"""Custom middleware and the usage callback for a turn (SPEC §6.5, §9)."""

import frappe
from frappe import _
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages.utils import count_tokens_approximately

from ai_assistant.llm import usage
from ai_assistant.persistence import dblock
from ai_assistant.services import budget, settings


class ConversationTooLongError(frappe.ValidationError):
	pass


@wrap_model_call
def token_budget(request: ModelRequest, handler) -> ModelResponse:
	"""Before each model call: the daily and monthly budgets, and the model's context window."""
	ctx = request.runtime.context
	with dblock.locked():
		if ctx.is_evaluation:
			budget.assert_site_budget()
		else:
			budget.assert_available()
		profile = settings.find_profile(ctx.model_profile)
	window = profile.context_window if profile else 0
	if window and count_tokens_approximately(request.messages) > window:
		frappe.throw(_("This conversation is too long. Start a new one."), ConversationTooLongError)
	return handler(request)


class UsageRecorder(BaseCallbackHandler):
	"""Writes AI Usage Log for every chat model call of a turn, including summaries."""

	def __init__(self, *, profile_id: str, conversation: str | None, purpose: str = "agent"):
		self.profile_id = profile_id
		self.conversation = conversation
		self.purpose = purpose
		self.input_tokens = 0
		self.output_tokens = 0
		self.cost = 0.0

	def on_llm_end(self, response, **kwargs):
		for generations in response.generations:
			for generation in generations:
				message = getattr(generation, "message", None)
				if message is None:
					continue
				input_tokens, output_tokens = usage.tokens_of(message)
				if not (input_tokens or output_tokens):
					continue
				with dblock.locked():
					self.cost += usage.record(
						profile_id=self.profile_id,
						purpose=self.purpose,
						input_tokens=input_tokens,
						output_tokens=output_tokens,
						conversation=self.conversation,
					)
				self.input_tokens += input_tokens
				self.output_tokens += output_tokens
