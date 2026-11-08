# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ai_assistant.services import agents


class AIAgent(Document):
	def validate(self):
		"""See frappe.model.document.Document.validate."""
		agents.validate(self)

	def on_update(self):
		"""See frappe.model.document.Document.on_update."""
		agents.on_update(self)
