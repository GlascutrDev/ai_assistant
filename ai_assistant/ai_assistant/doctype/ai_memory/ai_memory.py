# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ai_assistant.services import memory


class AIMemory(Document):
	def validate(self):
		"""See frappe.model.document.Document.validate."""
		memory.validate(self)
