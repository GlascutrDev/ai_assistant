# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ai_assistant.rag import web


class AIKnowledgeDocument(Document):
	def validate(self):
		"""See frappe.model.document.Document.validate."""
		if self.source_url and self.has_value_changed("source_url"):
			web.check_url(self.source_url)

	def on_update(self):
		"""See frappe.model.document.Document.on_update."""
		web.enqueue_refresh(self)
