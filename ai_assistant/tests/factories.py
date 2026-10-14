"""Test data builders. Tests run inside IntegrationTestCase, which rolls back."""

import frappe

from ai_assistant.services import settings as app_settings

FAKE_PROVIDER = "Fake OpenAI"


def assistant_user(
	email: str | None = None, roles=("AI Assistant User",), user_permissions: dict | None = None
):
	email = email or f"ai-{frappe.generate_hash(length=8)}@example.com"
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	for allow, value in (user_permissions or {}).items():
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": allow, "for_value": value}
		).insert(ignore_permissions=True)
	return email


def role(name: str = "AI Test Role") -> str:
	if not frappe.db.exists("Role", name):
		frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
			ignore_permissions=True
		)
	return name


def configure(**values):
	"""Enable the assistant with fake provider and profile rows, plus any Settings overrides."""
	doc = frappe.get_single(app_settings.SETTINGS)
	doc.providers = []
	doc.models = []
	doc.append(
		"providers",
		{"provider": "OpenAI", "label": FAKE_PROVIDER, "api_key": "sk-test-not-a-real-key", "enabled": 1},
	)
	for profile in (
		_chat("fake-main"),
		_chat("fake-eval"),
		_chat("fake-candidate"),
		{"profile_id": "fake-embed", "model_name": "fake-embed", "model_type": "Embedding", "dimensions": 8},
		{"profile_id": "fake-speech", "model_name": "fake-speech", "model_type": "Speech-to-text"},
	):
		doc.append("models", {"provider_label": FAKE_PROVIDER, "enabled": 1, **profile})
	doc.update(
		{
			"enabled": 1,
			"allowed_roles": [],
			"knowledge_sources": [],
			"blocked_doctypes": "\n".join(app_settings.DEFAULT_BLOCKED_DOCTYPES),
			"main_model": "fake-main",
			"evaluation_model": "fake-eval",
			"embedding_model": "fake-embed",
			"speech_model": "fake-speech",
			"read_only_mode": 0,
			"rag_enabled": 0,
			"voice_enabled": 0,
			"attachments_enabled": 0,
			"langsmith_enabled": 0,
			"user_daily_token_limit": 0,
			"site_monthly_cost_limit": 0,
			"index_stale": 0,
		}
	)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.clear_document_cache(app_settings.SETTINGS, app_settings.SETTINGS)
	return doc


def _chat(profile_id: str) -> dict:
	return {
		"profile_id": profile_id,
		"model_name": profile_id,
		"model_type": "Chat",
		"supports_tools": 1,
		"supports_images": 1,
		"supports_pdf": 1,
		"max_output_tokens": 1024,
		"context_window": 100000,
		"input_cost_per_mtok": 1,
		"output_cost_per_mtok": 2,
	}


def todo(description: str = "Test ToDo", **values):
	return frappe.get_doc({"doctype": "ToDo", "description": description, **values}).insert()


def note(title: str | None = None, **values):
	return frappe.get_doc(
		{"doctype": "Note", "title": title or f"Note {frappe.generate_hash(length=6)}", **values}
	).insert()
