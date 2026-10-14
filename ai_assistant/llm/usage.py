"""Record model usage in AI Usage Log and keep the budget counters current (SPEC §9)."""

import frappe
from frappe.utils import flt, nowdate

from ai_assistant.services import settings


def record(
	*,
	profile_id: str,
	purpose: str,
	input_tokens: int = 0,
	output_tokens: int = 0,
	audio_seconds: float = 0,
	conversation: str | None = None,
	user: str | None = None,
) -> float:
	profile = settings.find_profile(profile_id)
	cost = compute_cost(profile, input_tokens, output_tokens, audio_seconds)
	frappe.get_doc(
		{
			"doctype": "AI Usage Log",
			"date": nowdate(),
			"user": user or frappe.session.user,
			"conversation": conversation,
			"purpose": purpose,
			"profile_id": profile_id,
			"provider": profile and profile.provider_label,
			"model_name": profile and profile.model_name,
			"input_tokens": input_tokens,
			"output_tokens": output_tokens,
			"audio_seconds": audio_seconds,
			"cost": cost,
		}
	).insert(ignore_permissions=True)
	from ai_assistant.services import budget

	budget.add(user or frappe.session.user, input_tokens + output_tokens, cost, purpose)
	return cost


def compute_cost(profile, input_tokens: int, output_tokens: int, audio_seconds: float = 0) -> float:
	if not profile:
		return 0.0
	return (
		flt(input_tokens) / 1e6 * flt(profile.input_cost_per_mtok)
		+ flt(output_tokens) / 1e6 * flt(profile.output_cost_per_mtok)
		+ flt(audio_seconds) / 60 * flt(profile.cost_per_audio_minute)
	)


def tokens_of(message) -> tuple[int, int]:
	"""(input, output) tokens from an AIMessage's usage_metadata."""
	meta = getattr(message, "usage_metadata", None) or {}
	return int(meta.get("input_tokens") or 0), int(meta.get("output_tokens") or 0)
