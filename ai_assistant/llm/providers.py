"""Provider → LangChain mapping (SPEC §6.2). Add a provider here and in AI Provider Credential.provider."""

from dataclasses import dataclass

THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"


@dataclass(frozen=True)
class ProviderSpec:
	model_provider: str
	default_base_url: str | None = None
	needs_key: bool = True
	embeddings: bool = False
	speech: bool = False


PROVIDERS: dict[str, ProviderSpec] = {
	"Anthropic": ProviderSpec("anthropic"),
	"OpenAI": ProviderSpec("openai", embeddings=True, speech=True),
	"Moonshot": ProviderSpec("openai", default_base_url="https://api.moonshot.ai/v1"),
	"Google Gemini": ProviderSpec("google_genai", embeddings=True, speech=True),
	"DeepSeek": ProviderSpec("deepseek"),
	"Mistral": ProviderSpec("mistralai", embeddings=True),
	"Ollama": ProviderSpec(
		"ollama", default_base_url="http://localhost:11434", needs_key=False, embeddings=True
	),
	"OpenAI Compatible": ProviderSpec("openai", embeddings=True, speech=True),
}


def spec(provider: str) -> ProviderSpec:
	return PROVIDERS[provider]


def chat_kwargs(
	provider: str, *, api_key, base_url, max_tokens, temperature, timeout, organization=None
) -> dict:
	"""Constructor kwargs for the provider's chat class, built from one profile + credential."""
	base_url = base_url or spec(provider).default_base_url
	if provider == "Ollama":
		kw = {"base_url": base_url, "client_kwargs": {"timeout": timeout}}
		if max_tokens:
			kw["num_predict"] = max_tokens
	else:
		kw = {"api_key": api_key, "timeout": timeout, "max_retries": 2}
	if temperature is not None:
		kw["temperature"] = temperature
	if provider == "Ollama":
		return kw
	if max_tokens:
		kw["max_tokens"] = max_tokens
	if base_url and provider != "Google Gemini":
		kw["base_url"] = base_url
	if organization and provider == "OpenAI":
		kw["organization"] = organization
	return kw


def adapt_chat_model(provider: str, model):
	"""Make Anthropic drop stored thinking blocks that no longer match instead of failing the turn.

	A thinking block is bound to the system prompt it was made with, and ours changes between turns
	(clock, Desk page, attachments). Only adaptive-thinking models (profile has `xhigh`) accept this.
	"""
	if provider != "Anthropic" or "xhigh" not in ((model.profile or {}).get("reasoning_effort_levels") or ()):
		return model
	thinking = {
		**(model.thinking or {"type": "adaptive"}),
		"block_binding": {"prefix_mismatch_behavior": "drop_block"},
	}
	betas = [*(model.betas or []), THINKING_BINDING_BETA]
	return model.model_copy(update={"thinking": thinking, "betas": betas})


def embedding_kwargs(provider: str, *, api_key, base_url, dimensions, timeout) -> dict:
	base_url = base_url or spec(provider).default_base_url
	if provider == "Ollama":
		return {"base_url": base_url}
	kw = {"api_key": api_key}
	if provider in ("OpenAI", "OpenAI Compatible"):
		kw["timeout"] = timeout
		if base_url:
			kw["base_url"] = base_url
		if provider == "OpenAI" and dimensions:
			kw["dimensions"] = dimensions
		if provider == "OpenAI Compatible":
			kw["check_embedding_ctx_length"] = False
	if provider == "Google Gemini" and dimensions:
		kw["output_dimensionality"] = dimensions
	return kw
