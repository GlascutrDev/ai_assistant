"""Build the agent graph for one turn (SPEC §5, §6). Intake and finalize run in agent/runner.py."""

from langchain.agents import create_agent
from langchain.agents.middleware import (
	HumanInTheLoopMiddleware,
	ModelCallLimitMiddleware,
	SummarizationMiddleware,
	ToolCallLimitMiddleware,
)

from ai_assistant import tools
from ai_assistant.agent import middleware, prompts
from ai_assistant.agent.attachments import attachments_inliner
from ai_assistant.agent.context import TurnContext
from ai_assistant.llm import registry
from ai_assistant.persistence.checkpointer import FrappeCheckpointSaver
from ai_assistant.services import settings

DECISIONS = ["approve", "edit", "reject"]


def build(ctx: TurnContext, attachments: list[dict] | None = None):
	"""The agent for this turn. `ctx.model_profile` is the main model, or the target in an evaluation."""
	conf = settings.get()
	model = registry.get_chat_model(ctx.model_profile)
	turn_tools = tools.for_turn(
		read_only=bool(conf.read_only_mode), rag=bool(conf.rag_enabled), files=bool(conf.attachments_enabled)
	)
	write_names = {t.name for t in turn_tools} & tools.write_tool_names()
	stack = [
		attachments_inliner,
		middleware.token_budget,
		SummarizationMiddleware(
			model=model, trigger=("tokens", summarize_at(ctx.model_profile)), keep=("messages", 10)
		),
		ModelCallLimitMiddleware(run_limit=conf.max_model_calls_per_turn or 12, exit_behavior="end"),
		ToolCallLimitMiddleware(run_limit=conf.max_tool_calls_per_turn or 20, exit_behavior="end"),
	]
	if write_names:
		stack.append(
			HumanInTheLoopMiddleware(
				interrupt_on={name: {"allowed_decisions": DECISIONS} for name in sorted(write_names)},
				description_prefix="Confirm this change",
			)
		)
	return create_agent(
		model,
		tools=turn_tools,
		system_prompt=prompts.system(ctx, attachments),
		middleware=stack,
		context_schema=TurnContext,
		checkpointer=FrappeCheckpointSaver(),
	)


def summarize_at(profile_id: str) -> int:
	"""Summarize above `summarize_after_tokens` or 70 % of the model's context window, whichever is lower."""
	limit = settings.get().summarize_after_tokens or 60000
	profile = settings.find_profile(profile_id)
	if profile and profile.context_window:
		limit = min(limit, int(profile.context_window * 0.7))
	return limit
