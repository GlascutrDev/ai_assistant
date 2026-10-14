"""Background job entry points with no heavy imports, so a turn that cannot even load still ends cleanly."""

import frappe
from frappe import _


def run_turn(conversation: str, message: str | None = None, resume: dict | None = None):
	try:
		from ai_assistant.agent import runner
	except Exception:
		frappe.log_error(f"AI Assistant could not load the agent ({conversation})")
		_fail(conversation)
		return
	runner.run_turn(conversation, message=message, resume=resume)


def _fail(conversation: str):
	from ai_assistant.agent.stream import Publisher
	from ai_assistant.services import conversations

	message = _("The assistant could not start. Ask your administrator to check the Error Log.")
	conversations.add_message(conversation, "system_note", message)
	conversations.set_status(conversation, "Active")
	Publisher(conversation, frappe.session.user).error(message)
	if not frappe.in_test:
		frappe.db.commit()
