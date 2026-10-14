"""One small call to check a provider row from the Settings form."""

import frappe
from frappe import _

from ai_assistant.llm import registry, usage
from ai_assistant.services import settings


def test(label: str) -> dict:
	credential = next((row for row in settings.get().providers if row.label == label), None)
	if not credential:
		frappe.throw(_("No provider row with label {0}. Save the settings first.").format(label))
	profile = _profile_for(label)
	if not profile:
		return {"ok": False, "error": _("Add a Chat or Embedding model profile for {0} first.").format(label)}
	try:
		if profile.model_type == "Chat":
			reply = registry._build_chat(profile, credential).invoke("Reply with the single word: ok")
			input_tokens, output_tokens = usage.tokens_of(reply)
			usage.record(
				profile_id=profile.profile_id,
				purpose="test",
				input_tokens=input_tokens,
				output_tokens=output_tokens,
			)
			detail = (reply.text or "")[:100]
		else:
			vector = registry._build_embeddings(profile, credential).embed_query("ok")
			detail = _("{0} dimensions").format(len(vector))
	except Exception as e:
		return {
			"ok": False,
			"profile": profile.profile_id,
			"error": registry.redact(_error_text(e), credential),
		}
	return {"ok": True, "profile": profile.profile_id, "detail": detail}


def _profile_for(label: str):
	rows = [row for row in settings.get().models if row.provider_label == label]
	rows.sort(key=lambda row: (row.model_type != "Chat", row.model_type != "Embedding", not row.enabled))
	return next((row for row in rows if row.model_type in ("Chat", "Embedding")), None)


def _error_text(e: Exception) -> str:
	return f"{type(e).__name__}: {str(e)[:500]}"
