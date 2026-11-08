# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ai_assistant.services import automations


class AIAutomation(Document):
	def validate(self):
		"""See frappe.model.document.Document.validate."""
		automations.validate(self)

	def on_update(self):
		"""See frappe.model.document.Document.on_update."""
		automations.clear_cache()

	def on_trash(self):
		"""See frappe.model.document.Document.on_trash."""
		automations.clear_cache()
