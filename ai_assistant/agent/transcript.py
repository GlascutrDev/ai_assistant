"""Graph messages ↔ AI Message rows, conversation totals, and the title (SPEC §4.8)."""

import json

import frappe
from frappe.utils import flt
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ai_assistant.agent import prompts
from ai_assistant.llm import registry, usage
from ai_assistant.services import conversations

TOOL_CONTENT_CHARS = 4000
DENIED = ("permission_denied", "blocked_doctype")


def human_message(doc) -> HumanMessage:
	"""The graph input for a user AI Message. Attachments are references only (SPEC §6.8)."""
	names = [row.attachment for row in doc.attachments or []]
	kwargs = {"attachments": names} if names else {}
	return HumanMessage(content=doc.content, id=f"ai-message-{doc.name}", additional_kwargs=kwargs)


def attachments_of(conversation: str | None) -> list[dict]:
	if not conversation:
		return []
	return frappe.get_all(
		"AI Attachment",
		filters={"conversation": conversation, "status": "Ready", "kind": ["!=", "voice"]},
		fields=["name", "file_name", "kind", "delivery"],
		order_by="creation asc",
	)


def persist(conversation: str, messages: list, profile_id: str, run_id: str | None = None):
	calls = {}
	for m in messages:
		if isinstance(m, AIMessage):
			for call in m.tool_calls:
				calls[call["id"]] = call
			if m.text:
				input_tokens, output_tokens = usage.tokens_of(m)
				conversations.add_message(
					conversation,
					"assistant",
					m.text,
					model=profile_id,
					input_tokens=input_tokens,
					output_tokens=output_tokens,
					langsmith_run_id=run_id,
				)
		elif isinstance(m, ToolMessage):
			call = calls.get(m.tool_call_id) or {}
			conversations.add_message(
				conversation,
				"tool",
				(m.text or "")[:TOOL_CONTENT_CHARS],
				tool_name=m.name or call.get("name"),
				tool_args=json.dumps(call.get("args") or {}, default=str),
				tool_status=tool_status(m),
			)


def tool_status(m: ToolMessage) -> str:
	if getattr(m, "status", None) == "error":
		return "error"
	try:
		content = json.loads(m.text or "{}")
	except ValueError:
		return "ok"
	if isinstance(content, dict):
		if content.get("outcome") in DENIED:
			return "denied"
		if content.get("error"):
			return "error"
	return "ok"


def add_usage(conversation: str, recorder, profile_id: str):
	if not recorder or not (recorder.input_tokens or recorder.output_tokens):
		return
	conv = frappe.db.get_value(
		"AI Conversation",
		conversation,
		["total_input_tokens", "total_output_tokens", "total_cost"],
		as_dict=True,
	)
	frappe.db.set_value(
		"AI Conversation",
		conversation,
		{
			"total_input_tokens": (conv.total_input_tokens or 0) + recorder.input_tokens,
			"total_output_tokens": (conv.total_output_tokens or 0) + recorder.output_tokens,
			"total_cost": flt(conv.total_cost) + recorder.cost,
			"main_model": profile_id,
		},
	)


def set_title(conversation: str, first_message: str, profile_id: str):
	text = frappe.db.get_value("AI Message", first_message, "content") or ""
	title = text.strip().splitlines()[0][:60] if text.strip() else conversation
	try:
		reply = registry.get_chat_model(profile_id).invoke(prompts.TITLE_PROMPT.format(text=text[:1000]))
		input_tokens, output_tokens = usage.tokens_of(reply)
		usage.record(
			profile_id=profile_id,
			purpose="title",
			input_tokens=input_tokens,
			output_tokens=output_tokens,
			conversation=conversation,
		)
		lines = (reply.text or "").strip().strip('"').splitlines()
		title = (lines[0][:80] if lines else "") or title
	except Exception:
		frappe.log_error("AI Assistant title generation failed")
	frappe.db.set_value("AI Conversation", conversation, "title", title)
