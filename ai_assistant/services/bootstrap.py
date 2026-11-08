"""What the chat UI needs at start (SPEC §12 get_bootstrap)."""

import frappe
from frappe import _

from ai_assistant.services import access, agents, budget, settings


def get() -> dict:
	user = frappe.session.user
	conf = settings.get()
	if user == "Guest" or not access.has_access(user):
		return {"enabled": False, "reason": _("You do not have access to the AI Assistant.")}
	if not conf.enabled:
		reason = _("The AI Assistant is switched off.")
		if access.is_admin(user):
			reason = setup_hint(conf)
		return {"enabled": False, "reason": reason, "is_admin": access.is_admin(user)}
	main = settings.find_profile(conf.main_model)
	return {
		"enabled": True,
		"assistant_name": conf.assistant_name or "AI Assistant",
		"main_model": main.profile_id if main else None,
		"tokens_left_today": budget.tokens_left_today(user),
		"read_only": bool(conf.read_only_mode),
		"voice_enabled": bool(conf.voice_enabled),
		"voice_auto_send": bool(conf.voice_auto_send),
		"max_voice_seconds": conf.max_voice_seconds or 120,
		"attachments_enabled": bool(conf.attachments_enabled),
		"allowed_file_types": sorted(settings.allowed_file_types()),
		"max_file_size_mb": conf.max_file_size_mb or 20,
		"max_files_per_message": conf.max_files_per_message or 5,
		"supports_images": bool(main and main.supports_images),
		"supports_pdf": bool(main and main.supports_pdf),
		"is_admin": access.is_admin(user),
		"agents": agents.available(user),
	}


def setup_hint(conf) -> str:
	"""What a System Manager still has to do before the assistant can be enabled."""
	main = settings.find_profile(conf.main_model)
	provider = main and next((p for p in conf.providers if p.label == main.provider_label), None)
	if not main:
		return _("Choose a Main Model in AI Assistant Settings.")
	if not provider or not provider.enabled:
		return _("Enable the provider {0} and enter its API key in AI Assistant Settings.").format(
			main.provider_label
		)
	if not main.enabled:
		return _("Tick Enabled on the model {0} (Models tab), then tick Enabled on the General tab.").format(
			main.profile_id
		)
	return _("Tick Enabled on the General tab of AI Assistant Settings and save.")
