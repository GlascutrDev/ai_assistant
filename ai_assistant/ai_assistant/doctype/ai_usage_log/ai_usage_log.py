# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ai_assistant.services.append_only import AppendOnlyDocument


class AIUsageLog(AppendOnlyDocument, Document):
	pass
