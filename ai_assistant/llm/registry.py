"""Build chat and embedding models from AI Assistant Settings. The only place API keys are read (rule 7)."""

import frappe
from frappe import _

from ai_assistant.llm import providers
from ai_assistant.services import settings

_cache: dict[tuple, object] = {}


class ModelNotConfiguredError(frappe.ValidationError):
	pass


def get_main_model():
	return get_chat_model(settings.get().main_model)


def get_evaluation_model():
	"""The test/evaluation model. Call only from ai_assistant/evals (rule 8)."""
	return get_chat_model(settings.get().evaluation_model)


def get_chat_model(profile_id: str | None):
	profile, credential = resolve(profile_id, "Chat")
	return _cached(("chat", profile_id), lambda: _build_chat(profile, credential))


def get_embeddings():
	profile, credential = resolve(settings.get().embedding_model, "Embedding")
	return _cached(("embed", profile.profile_id), lambda: _build_embeddings(profile, credential))


def resolve(profile_id: str | None, model_type: str):
	"""Return (profile row, credential row) for an enabled profile of the given type."""
	profile = settings.find_profile(profile_id)
	if not profile or not profile.enabled or profile.model_type != model_type:
		frappe.throw(
			_("No enabled {0} model profile {1}. Check AI Assistant Settings.").format(
				_(model_type), profile_id or ""
			),
			ModelNotConfiguredError,
		)
	credential = next((row for row in settings.get().providers if row.label == profile.provider_label), None)
	if not credential or not credential.enabled:
		frappe.throw(
			_("Provider {0} is not enabled. Check AI Assistant Settings.").format(profile.provider_label),
			ModelNotConfiguredError,
		)
	return profile, credential


def api_key(credential) -> str | None:
	return credential.get_password("api_key", raise_exception=False) or None


def redact(text: str, credential=None) -> str:
	"""Remove the credential's key from an error message before it is shown or logged."""
	key = credential and api_key(credential)
	return text.replace(key, "***") if key else text


def clear_cache():
	_cache.clear()


def _cached(key: tuple, build):
	full_key = (frappe.local.site, str(settings.get().modified), *key)
	if full_key not in _cache:
		_drop_stale(full_key)
		_cache[full_key] = build()
	return _cache[full_key]


def _drop_stale(full_key: tuple):
	for old in [k for k in _cache if k[0] == full_key[0] and k[2:] == full_key[2:]]:
		del _cache[old]


def _build_chat(profile, credential):
	from langchain.chat_models import init_chat_model

	spec = providers.spec(credential.provider)
	kwargs = providers.chat_kwargs(
		credential.provider,
		api_key=api_key(credential),
		base_url=credential.base_url,
		max_tokens=profile.max_output_tokens,
		temperature=profile.temperature,
		timeout=profile.timeout_seconds or 120,
		organization=credential.organization,
	)
	return init_chat_model(profile.model_name, model_provider=spec.model_provider, **kwargs)


def _build_embeddings(profile, credential):
	from langchain.embeddings import init_embeddings

	spec = providers.spec(credential.provider)
	if not spec.embeddings:
		frappe.throw(_("Provider {0} has no embedding models.").format(credential.provider))
	kwargs = providers.embedding_kwargs(
		credential.provider,
		api_key=api_key(credential),
		base_url=credential.base_url,
		dimensions=profile.dimensions,
		timeout=profile.timeout_seconds or 120,
	)
	return init_embeddings(profile.model_name, provider=spec.model_provider, **kwargs)
