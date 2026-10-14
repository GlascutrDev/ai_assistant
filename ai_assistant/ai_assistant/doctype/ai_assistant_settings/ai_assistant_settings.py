# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

SPEECH_PROVIDERS = ("OpenAI", "OpenAI Compatible", "Google Gemini")
EMBEDDING_PROVIDERS = ("OpenAI", "Google Gemini", "Mistral", "Ollama", "OpenAI Compatible")


class AIAssistantSettings(Document):
	def validate(self):
		"""See frappe.model.document.Document.validate."""
		self._validate_unique("providers", "label", _("Provider label"))
		self._validate_unique("models", "profile_id", _("Profile ID"))
		self._validate_provider_rows()
		self._validate_model_rows()
		self._validate_choices()
		self._mark_index_stale()

	def on_update(self):
		"""See frappe.model.document.Document.on_update."""
		from ai_assistant.llm import registry
		from ai_assistant.rag import indexer

		registry.clear_cache()
		indexer.clear_source_cache()

	def provider_row(self, label: str | None):
		return next((row for row in self.providers if row.label == label), None)

	def profile_row(self, profile_id: str | None):
		return next((row for row in self.models if row.profile_id == profile_id), None)

	def _validate_unique(self, table: str, field: str, title: str):
		seen = set()
		for row in self.get(table):
			value = (row.get(field) or "").strip()
			if value in seen:
				frappe.throw(_("{0} {1} is used twice.").format(title, frappe.bold(value)))
			seen.add(value)

	def _validate_provider_rows(self):
		for row in self.providers:
			if row.provider == "OpenAI Compatible" and not row.base_url:
				frappe.throw(_("Provider {0}: Base URL is required for OpenAI Compatible.").format(row.label))

	def _validate_model_rows(self):
		for row in self.models:
			if not row.enabled:
				continue
			provider = self.provider_row(row.provider_label)
			if not provider:
				frappe.throw(
					_("Model {0}: no provider row with label {1}.").format(row.profile_id, row.provider_label)
				)
			if not provider.enabled:
				frappe.throw(_("Model {0}: provider {1} is disabled.").format(row.profile_id, provider.label))
			if row.model_type == "Embedding" and not row.dimensions:
				frappe.throw(
					_("Model {0}: dimensions are required for an embedding model.").format(row.profile_id)
				)

	def _validate_choices(self):
		if self.enabled or self.main_model:
			self._require_chat(self.main_model, _("Main Model"), required=bool(self.enabled))
		if self.evaluation_model:
			self._require_chat(self.evaluation_model, _("Test/Evaluation Model"), required=False)
		if self.enabled and self.evaluation_model and self.evaluation_model == self.main_model:
			frappe.msgprint(
				_(
					"The test/evaluation model is the same as the main model. A model that grades its own "
					"answers scores them too high. A different provider is recommended."
				),
				indicator="orange",
				alert=True,
			)
		if self.rag_enabled or self.attachments_enabled:
			self._require_type(self.embedding_model, "Embedding", _("Embedding Model"), self.rag_enabled)
			self._check_provider_in(self.embedding_model, EMBEDDING_PROVIDERS, _("embeddings"))
		if self.voice_enabled:
			self._require_type(self.speech_model, "Speech-to-text", _("Speech Model"), True)
			self._check_provider_in(self.speech_model, SPEECH_PROVIDERS, _("speech-to-text"))
		if self.evaluation_user and "System Manager" in frappe.get_roles(self.evaluation_user):
			frappe.throw(_("The evaluation user must not be Administrator or a System Manager."))

	def _require_chat(self, profile_id, title, required):
		row = self._require_type(profile_id, "Chat", title, required)
		if row and not row.supports_tools:
			frappe.throw(_("{0}: profile {1} must support tools.").format(title, profile_id))

	def _require_type(self, profile_id, model_type, title, required):
		if not profile_id:
			if required:
				frappe.throw(_("{0} is required.").format(title))
			return None
		row = self.profile_row(profile_id)
		if not row:
			frappe.throw(_("{0}: no model profile {1}.").format(title, profile_id))
		if row.model_type != model_type:
			frappe.throw(_("{0}: profile {1} must be of type {2}.").format(title, profile_id, model_type))
		if required and not row.enabled:
			frappe.throw(_("{0}: profile {1} is disabled.").format(title, profile_id))
		return row

	def _check_provider_in(self, profile_id, providers, purpose):
		row = self.profile_row(profile_id)
		provider = row and self.provider_row(row.provider_label)
		if provider and provider.provider not in providers:
			frappe.throw(_("Provider {0} does not support {1}.").format(provider.provider, purpose))

	def _mark_index_stale(self):
		before = self.get_doc_before_save()
		if not before:
			return
		old = before.profile_row(before.embedding_model)
		new = self.profile_row(self.embedding_model)
		old_key = (before.embedding_model, old and old.model_name, old and old.dimensions)
		new_key = (self.embedding_model, new and new.model_name, new and new.dimensions)
		if old_key != new_key:
			self.index_stale = 1
