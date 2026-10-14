"""AI Action Request: paused writes and the user's decisions (SPEC §4.9, §6.5, §7.2)."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

OPERATIONS = {
	"create_document": "create",
	"update_document": "update",
	"submit_document": "submit",
	"cancel_document": "cancel",
	"delete_document": "delete",
	"add_comment": "comment",
	"assign_to": "assign",
	"apply_workflow_action": "workflow",
	"attach_file": "attach",
}

CARD_FIELDS = [
	"name",
	"tool_name",
	"operation",
	"target_doctype",
	"target_name",
	"proposed_args",
	"diff_html",
	"status",
	"interrupt_id",
	"action_index",
]


def create_from_interrupt(conversation: str, interrupt) -> list[dict]:
	"""One Pending request per action of a HumanInTheLoop interrupt, in the interrupt's order."""
	from ai_assistant.tools import write

	cards = []
	for index, action in enumerate(interrupt.value.get("action_requests", [])):
		args = action.get("args") or {}
		target_doctype, target_name = write.target_of(action["name"], args)
		doc = frappe.get_doc(
			{
				"doctype": "AI Action Request",
				"conversation": conversation,
				"user": frappe.session.user,
				"tool_name": action["name"],
				"operation": OPERATIONS.get(action["name"]),
				"target_doctype": target_doctype,
				"target_name": target_name,
				"proposed_args": json.dumps(args, default=str),
				"diff_html": write.preview_html(action["name"], args),
				"status": "Pending",
				"interrupt_id": interrupt.id,
				"action_index": index,
			}
		).insert(ignore_permissions=True)
		cards.append(_card(doc))
	return cards


def pending_for(conversation: str) -> list[dict]:
	return frappe.get_all(
		"AI Action Request",
		filters={"conversation": conversation, "status": "Pending"},
		fields=CARD_FIELDS,
		order_by="action_index asc",
	)


def _card(doc) -> dict:
	return {f: doc.get(f) for f in CARD_FIELDS}


def _now():
	return now_datetime()
