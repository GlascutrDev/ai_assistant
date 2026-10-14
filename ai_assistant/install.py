import frappe

from ai_assistant.persistence import schema
from ai_assistant.services import settings

DEFAULT_PROVIDERS = (
	{"provider": "Anthropic", "label": "Anthropic"},
	{"provider": "OpenAI", "label": "OpenAI"},
)

DEFAULT_MODELS = (
	{
		"profile_id": "claude-main",
		"provider_label": "Anthropic",
		"model_name": "claude-sonnet-5-5",
		"model_type": "Chat",
		"max_output_tokens": 8192,
		"context_window": 200000,
		"supports_tools": 1,
		"supports_images": 1,
		"supports_pdf": 1,
	},
	{
		"profile_id": "gpt-eval",
		"provider_label": "OpenAI",
		"model_name": "gpt-5.5",
		"model_type": "Chat",
		"max_output_tokens": 4096,
		"context_window": 200000,
		"supports_tools": 1,
		"supports_images": 1,
	},
	{
		"profile_id": "oai-embed",
		"provider_label": "OpenAI",
		"model_name": "text-embedding-3-small",
		"model_type": "Embedding",
		"dimensions": 1536,
	},
	{
		"profile_id": "oai-transcribe",
		"provider_label": "OpenAI",
		"model_name": "gpt-4o-transcribe",
		"model_type": "Speech-to-text",
	},
)


def after_install():
	ensure_role()
	set_default_settings()
	schema.ensure_tables()


def after_migrate():
	ensure_role()
	schema.ensure_tables()


def ensure_role():
	if frappe.db.exists("Role", settings.ASSISTANT_ROLE):
		return
	frappe.get_doc({"doctype": "Role", "role_name": settings.ASSISTANT_ROLE, "desk_access": 1}).insert(
		ignore_permissions=True
	)


def set_default_settings():
	doc = frappe.get_single(settings.SETTINGS)
	doc.blocked_doctypes = "\n".join(settings.DEFAULT_BLOCKED_DOCTYPES)
	doc.allowed_file_types = "\n".join(settings.DEFAULT_FILE_TYPES.split())
	doc.langsmith_project = f"ai_assistant-{frappe.local.site}"
	if not doc.providers:
		for row in DEFAULT_PROVIDERS:
			doc.append("providers", {**row, "enabled": 0})
	if not doc.models:
		for row in DEFAULT_MODELS:
			doc.append("models", {**row, "enabled": 0})
		doc.main_model = "claude-main"
		doc.evaluation_model = "gpt-eval"
		doc.embedding_model = "oai-embed"
		doc.speech_model = "oai-transcribe"
	doc.save(ignore_permissions=True)
