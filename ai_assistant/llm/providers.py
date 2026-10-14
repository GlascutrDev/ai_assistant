"""Provider → LangChain mapping (SPEC §6.2). Add a provider here and in AI Provider Credential.provider."""

from dataclasses import dataclass


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
		kw = {"base_url": base_url, "temperature": temperature, "client_kwargs": {"timeout": timeout}}
		if max_tokens:
			kw["num_predict"] = max_tokens
		return kw

	kw = {"api_key": api_key, "temperature": temperature, "timeout": timeout, "max_retries": 2}
	if max_tokens:
		kw["max_tokens"] = max_tokens
	if base_url and provider != "Google Gemini":
		kw["base_url"] = base_url
	if organization and provider == "OpenAI":
		kw["organization"] = organization
	return kw


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
	return kw
