"""Scripted chat model and deterministic embeddings. No test calls a real provider (rule 14)."""

import hashlib
import math
import re
from contextlib import contextmanager
from unittest.mock import patch

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeChatModel(BaseChatModel):
	"""Returns the scripted responses in order, then "Done.".

	A response is an AIMessage, a string, or a callable(messages) -> AIMessage | str.
	"""

	responses: list = []
	calls: list = []
	name: str = "fake"
	raise_error: bool = False
	bound_tools: list = []

	@property
	def _llm_type(self) -> str:
		return "fake-chat"

	def bind_tools(self, tools, **kwargs):
		self.bound_tools = [getattr(t, "name", None) or t.get("name") for t in tools]
		return self

	def _generate(self, messages, stop=None, run_manager=None, **kwargs):
		if self.raise_error:
			raise RuntimeError(f"{self.name} must not be called")
		self.calls.append(list(messages))
		response = self.responses.pop(0) if self.responses else "Done."
		if callable(response):
			response = response(messages)
		if isinstance(response, str):
			response = AIMessage(content=response)
		if not response.usage_metadata:
			response.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
		return ChatResult(generations=[ChatGeneration(message=response)])


def fake_chat(*responses, name: str = "fake", raise_error: bool = False) -> FakeChatModel:
	return FakeChatModel(
		responses=list(responses), calls=[], name=name, raise_error=raise_error, bound_tools=[]
	)


def tool_call(name: str, args: dict, call_id: str | None = None) -> AIMessage:
	call_id = call_id or f"call_{name}_{hashlib.md5(repr(args).encode()).hexdigest()[:8]}"
	return AIMessage(
		content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}]
	)


class FakeEmbeddings(Embeddings):
	"""Bag-of-words hashing into `dim` dimensions, so similar texts are close."""

	def __init__(self, dim: int = 8):
		self.dim = dim

	def embed_documents(self, texts):
		return [self.embed_query(t) for t in texts]

	def embed_query(self, text):
		vector = [0.0] * self.dim
		for word in re.findall(r"\w+", text.lower()):
			vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
		norm = math.sqrt(sum(v * v for v in vector)) or 1.0
		return [v / norm for v in vector] if any(vector) else [1.0 / math.sqrt(self.dim)] * self.dim


@contextmanager
def use_models(chat: dict | None = None, embeddings: Embeddings | None = None):
	"""Patch the registry: `chat` maps profile_id → FakeChatModel."""
	from ai_assistant.llm import registry

	chat = chat or {}

	def build_chat(profile, credential):
		if profile.profile_id not in chat:
			raise AssertionError(f"Unexpected chat profile {profile.profile_id}")
		return chat[profile.profile_id]

	registry.clear_cache()
	with (
		patch.object(registry, "_build_chat", side_effect=build_chat),
		patch.object(registry, "_build_embeddings", side_effect=lambda p, c: embeddings or FakeEmbeddings()),
	):
		yield
	registry.clear_cache()


class FakeRuntime:
	"""Stands in for ToolRuntime when a test calls a conversation-scoped tool directly."""

	def __init__(self, user: str, conversation: str):
		from ai_assistant.agent.context import TurnContext

		self.context = TurnContext(user=user, conversation=conversation)
