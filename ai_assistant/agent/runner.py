"""Background job that runs one turn as the enqueuing user (SPEC §6.5)."""

from dataclasses import dataclass, field

import frappe
from frappe import _
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ai_assistant import tools
from ai_assistant.agent import graph, transcript
from ai_assistant.agent.context import TurnContext
from ai_assistant.agent.middleware import ConversationTooLongError, UsageRecorder
from ai_assistant.agent.stream import Publisher
from ai_assistant.llm.registry import ModelNotConfiguredError
from ai_assistant.observability import tracing
from ai_assistant.persistence import dblock
from ai_assistant.services import actions, conversations, settings
from ai_assistant.services.budget import BudgetExceededError

PROVIDER_ERROR = "The AI provider is not responding. Try again."
CANNOT_PREPARE = "The assistant could not prepare a valid action. Try again with more detail."
MAX_AUTO_RESUMES = 3


@dataclass
class TurnResult:
	messages: list = field(default_factory=list)
	interrupts: list = field(default_factory=list)
	cancelled: bool = False
	usage: UsageRecorder | None = None
	run_id: str | None = None


def run_turn(conversation: str, message: str | None = None, resume: dict | None = None):
	conv = conversations.load_own(conversation)
	publisher = Publisher(conv.name, conv.user)
	frappe.cache.delete_value(cancel_key(conv.name))
	ctx = TurnContext(
		user=frappe.session.user,
		conversation=conv.name,
		lang=frappe.local.lang or "en",
		model_profile=settings.get().main_model,
		desk_context={"doctype": conv.context_doctype, "name": conv.context_name}
		if conv.context_doctype
		else None,
	)
	try:
		if message:
			_close_open_interrupt(ctx)
		graph_input = Command(resume=resume) if resume else {"messages": [user_input(message)]}
		_run_passes(conv, ctx, graph_input, publisher, message)
	except (BudgetExceededError, ModelNotConfiguredError, ConversationTooLongError) as e:
		fail(conv.name, publisher, str(e))
	except Exception as e:
		frappe.log_error(f"AI Assistant turn failed ({conv.name})")
		fail(conv.name, publisher, provider_message(e))
	_commit()


PROVIDER_HINTS = (
	(
		("credit balance", "insufficient_quota", "credit_balance", "billing"),
		"The AI provider account has no credit left. Ask your administrator to add credit.",
	),
	(
		("authentication", "invalid x-api-key", "invalid api key", "incorrect api key", "401"),
		"The AI provider rejected the API key. Ask your administrator to check it.",
	),
	(("rate limit", "rate_limit", "429", "overloaded"), "The AI provider is busy. Try again in a minute."),
)


def provider_message(error: Exception) -> str:
	"""A user-facing reason for a failed model call. Never includes the error text itself."""
	text = f"{type(error).__name__} {error}".lower()
	for needles, message in PROVIDER_HINTS:
		if any(n in text for n in needles):
			return _(message)
	return _(PROVIDER_ERROR)


def cancel(conv):
	"""Stop a running turn, or reject the writes waiting for confirmation."""
	if conv.status == "Waiting for confirmation":
		actions.reject_open(conv.name, _("Cancelled by the user."))
		conversations.set_status(conv.name, "Active")
	else:
		request_cancel(conv.name)


def execute(
	ctx: TurnContext, graph_input, publisher: Publisher | None = None, purpose: str = "agent"
) -> TurnResult:
	"""Stream the graph for one turn and collect new messages and interrupts. Reused by evals."""
	dblock.bind_turn()
	agent = graph.build(ctx, transcript.attachments_of(ctx.conversation))
	recorder = UsageRecorder(profile_id=ctx.model_profile, conversation=ctx.conversation, purpose=purpose)
	result = TurnResult(usage=recorder)
	turn_tracer = tracing.tracer(ctx, purpose)
	config = {
		"configurable": {"thread_id": ctx.conversation},
		"callbacks": [recorder, turn_tracer] if turn_tracer else [recorder],
		"recursion_limit": 200,
	}
	try:
		_stream(agent, graph_input, config, ctx, result, publisher)
	finally:
		result.run_id = tracing.root_run_id(turn_tracer)
		tracing.flush(turn_tracer)
	return result


def _stream(agent, graph_input, config, ctx: TurnContext, result: TurnResult, publisher: Publisher | None):
	seen = set()
	for chunk in agent.stream(
		graph_input, config, context=ctx, stream_mode=["messages", "updates"], version="v2", durability="sync"
	):
		if ctx.conversation and _cancel_requested(ctx.conversation):
			result.cancelled = True
			break
		if chunk["type"] == "messages":
			token, meta = chunk["data"]
			if (
				publisher
				and meta.get("langgraph_node") == "model"
				and isinstance(token, AIMessage)
				and token.text
			):
				publisher.token(token.text)
			continue
		for node, update in chunk["data"].items():
			if node == "__interrupt__":
				result.interrupts.extend(update)
			elif isinstance(update, dict):
				_collect(update.get("messages") or [], seen, result, publisher)


def finalize(
	conv, ctx: TurnContext, result: TurnResult, publisher: Publisher, first_message: str | None = None
) -> list[dict] | None:
	"""Persist the pass. Returns resume decisions when every write of the interrupt failed its pre-check."""
	decisions = None
	with dblock.locked():
		transcript.persist(conv.name, result.messages, ctx.model_profile, run_id=result.run_id)
		transcript.add_usage(conv.name, result.usage, ctx.model_profile)
		actions.record_results(conv.name, [m for m in result.messages if isinstance(m, ToolMessage)])
		if result.cancelled:
			conversations.add_message(conv.name, "system_note", _("Stopped."))
			status = "Active"
		elif result.interrupts:
			cards = _action_cards(conv.name, result)
			if any(card["status"] == "Pending" for card in cards):
				status = "Waiting for confirmation"
				publisher.confirmation(cards)
			else:
				status = "Running"
				decisions = actions.decisions_for(conv.name, result.interrupts[-1].id)
		else:
			status = "Active"
		conversations.set_status(conv.name, status)
		if not conv.title and first_message:
			transcript.set_title(conv.name, first_message, ctx.model_profile)
	if decisions is None:
		publisher.done(status)
	return decisions


def _run_passes(conv, ctx: TurnContext, graph_input, publisher: Publisher, first_message: str | None):
	"""Resume in this job, not by enqueue: the running job holds the turn's job id, so the dedupe drops it."""
	for _attempt in range(MAX_AUTO_RESUMES + 1):
		result = execute(ctx, graph_input, publisher)
		decisions = finalize(conv, ctx, result, publisher, first_message=first_message)
		if decisions is None:
			return
		_commit()
		graph_input, first_message = Command(resume={"decisions": decisions}), None
	fail(conv.name, publisher, _(CANNOT_PREPARE))


def fail(conversation: str, publisher: Publisher, message: str):
	with dblock.locked():
		conversations.add_message(conversation, "system_note", message)
		conversations.set_status(conversation, "Active")
	publisher.error(message)


def _action_cards(conversation: str, result: TurnResult) -> list[dict]:
	write_names = tools.write_tool_names()
	calls = next(
		(m.tool_calls for m in reversed(result.messages) if isinstance(m, AIMessage) and m.tool_calls), []
	)
	call_ids = [c["id"] for c in calls if c["name"] in write_names]
	return [
		card for i in result.interrupts for card in actions.create_from_interrupt(conversation, i, call_ids)
	]


def _close_open_interrupt(ctx: TurnContext):
	"""A new message on a thread with an undecided interrupt rejects that interrupt first."""
	agent = graph.build(ctx)
	state = agent.get_state({"configurable": {"thread_id": ctx.conversation}})
	if not state.interrupts:
		return
	actions.reject_open(ctx.conversation, _("The user sent a new message instead."))
	count = len(state.interrupts[-1].value.get("action_requests", []))
	reject = {"type": "reject", "message": _("The user sent a new message instead of deciding.")}
	stale = execute(ctx, Command(resume={"decisions": [reject] * count}))
	with dblock.locked():
		transcript.persist(
			ctx.conversation, [m for m in stale.messages if isinstance(m, ToolMessage)], ctx.model_profile
		)


def user_input(message: str) -> HumanMessage:
	doc = frappe.get_doc("AI Message", message)
	return transcript.human_message(doc)


def request_cancel(conversation: str):
	frappe.cache.set_value(cancel_key(conversation), 1, expires_in_sec=3600)


def cancel_key(conversation: str) -> str:
	return f"ai_assistant:cancel:{conversation}"


def _cancel_requested(conversation: str) -> bool:
	return bool(frappe.cache.get_value(cancel_key(conversation)))


def _collect(messages: list, seen: set, result: TurnResult, publisher: Publisher | None):
	for m in messages:
		if not isinstance(m, AIMessage | ToolMessage):
			continue
		key = m.id or id(m)
		if key in seen:
			continue
		seen.add(key)
		result.messages.append(m)
		if not publisher:
			continue
		if isinstance(m, AIMessage):
			for call in m.tool_calls:
				publisher.step(call["name"], call["args"])
		else:
			publisher.tool_result(m.name, transcript.tool_status(m), transcript.tool_error(m))


def _commit():
	if not frappe.in_test:
		frappe.db.commit()
