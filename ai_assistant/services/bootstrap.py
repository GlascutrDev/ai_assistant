"""What the chat UI needs at start (SPEC §12 get_bootstrap)."""

import frappe

from ai_assistant.services import access, budget, settings


def get() -> dict:
	user = frappe.session.user
	conf = settings.get()
	if user == "Guest" or not conf.enabled or not access.has_access(user):
		return {"enabled": False}
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
	}
