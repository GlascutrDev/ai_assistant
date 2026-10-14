"""Voice prompts (SPEC §6.7): the recording is transcribed first; the agent receives text only."""

import frappe
from frappe import _

from ai_assistant.services import attachments


def check_for_message(conv, name: str):
	"""A voice recording sent with a message: this user's, this conversation's, transcribed, unsent."""
	att = attachments.load_own(name)
	if att.conversation != conv.name or att.kind != "voice":
		frappe.throw(_("This recording belongs to another conversation."), frappe.PermissionError)
	if att.status != "Ready" or att.sent:
		frappe.throw(_("This recording cannot be sent."))
	frappe.db.set_value("AI Attachment", att.name, "sent", 1)
