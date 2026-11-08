"""AI Action Request: paused writes and the user's decisions (SPEC §4.9, §6.5, §7.2)."""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from ai_assistant.services import conversations

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
	"write_spreadsheet": "create",
	"create_documents": "create",
	"update_documents": "update",
	"delete_documents": "delete",
	"send_email": "email",
	"remember": "create",
	"forget_memory": "delete",
}


def operation_of(tool_name: str) -> str | None:
	"""The operation of a core write tool, or of an extension write tool (its `ai_assistant` metadata)."""
	from ai_assistant import tools

	if tool_name in OPERATIONS:
		return OPERATIONS[tool_name]
	spec = tools.write_spec(tool_name)
	return spec["operation"] if spec else None


CARD_FIELDS = [
	"name",
	"tool_name",
	"operation",
	"target_doctype",
	"target_name",
	"proposed_args",
	"diff_html",
	"status",
	"result",
	"interrupt_id",
	"action_index",
]
DECIDED = ("Approved", "Edited", "Rejected", "Failed", "Expired")
OPEN = ("Pending", "Approved", "Edited")


def create_from_interrupt(conversation: str, interrupt, tool_call_ids: list[str]) -> list[dict]:
	"""One request per action of a HumanInTheLoop interrupt, in order. A write that would fail is
	recorded as Failed with the reason, so the card never offers it."""
	from ai_assistant.tools import preview

	cards = []
	for index, action in enumerate(interrupt.value.get("action_requests", [])):
		args = action.get("args") or {}
		error = preview.precheck(action["name"], args)
		target_doctype, target_name = preview.target_of(action["name"], args)
		doc = frappe.get_doc(
			{
				"doctype": "AI Action Request",
				"conversation": conversation,
				"user": frappe.session.user,
				"tool_name": action["name"],
				"operation": operation_of(action["name"]),
				"target_doctype": target_doctype,
				"target_name": target_name,
				"proposed_args": json.dumps(args, default=str),
				"diff_html": preview.preview_html(action["name"], args),
				"status": "Failed" if error else "Pending",
				"result": error,
				"decided_at": now_datetime() if error else None,
				"interrupt_id": interrupt.id,
				"tool_call_id": tool_call_ids[index] if index < len(tool_call_ids) else None,
				"action_index": index,
			}
		).insert(ignore_permissions=True)
		cards.append(_card(doc))
	return cards


def decide(name: str, decision: str, edited_args: dict | None = None, message: str | None = None) -> dict:
	"""Record the user's decision; resume the turn once every request of the interrupt is decided."""
	if decision not in ("approve", "edit", "reject"):
		frappe.throw(_("Decision must be approve, edit, or reject."))
	if not frappe.db.exists("AI Action Request", name):
		frappe.throw(_("Action request not found."), frappe.DoesNotExistError)
	request = frappe.get_doc("AI Action Request", name)
	conversations.load_own(request.conversation)
	if request.user != frappe.session.user:
		frappe.throw(_("Only the user of this conversation can decide."), frappe.PermissionError)
	frappe.db.get_value("AI Conversation", request.conversation, "status", for_update=True)
	request.reload()
	if request.status != "Pending":
		frappe.throw(_("This action was already decided ({0}).").format(_(request.status)))
	if decision == "edit" and not isinstance(edited_args, dict):
		frappe.throw(_("Edited arguments must be an object."))
	_set(
		request,
		status={"approve": "Approved", "edit": "Edited", "reject": "Rejected"}[decision],
		edited_args=json.dumps(edited_args, default=str) if decision == "edit" else None,
		decision_message=(message or "")[:1000] or None,
	)
	resumed = resume_if_complete(request.conversation, request.interrupt_id)
	return {"action_request": name, "status": request.status, "resumed": resumed}


def resume_if_complete(conversation: str, interrupt_id: str) -> bool:
	"""Enqueue the resumed turn. Call from a web request only: inside a turn job the dedupe drops it."""
	decisions = decisions_for(conversation, interrupt_id)
	if decisions is None:
		return False
	conversations.set_status(conversation, "Running")
	conversations.enqueue_turn(conversation, resume={"decisions": decisions})
	return True


def decisions_for(conversation: str, interrupt_id: str) -> list[dict] | None:
	"""The resume decisions of an interrupt, or None while any request is still Pending."""
	requests = _of_interrupt(conversation, interrupt_id)
	if any(r.status == "Pending" for r in requests):
		return None
	return [decision_of(r) for r in requests]


def decision_of(request) -> dict:
	if request.status == "Approved":
		return {"type": "approve"}
	if request.status == "Edited":
		args = json.loads(request.edited_args or "{}")
		return {"type": "edit", "edited_action": {"name": request.tool_name, "args": args}}
	reason = {
		"Failed": _("The action cannot run: {0}").format(request.result),
		"Expired": _("The user did not decide in time."),
	}.get(request.status)
	message = request.decision_message or reason or _("The user rejected this action.")
	return {"type": "reject", "message": message}


def record_results(conversation: str, tool_messages: list):
	"""After a resume: Executed or Failed for each approved request, from its tool result."""
	from ai_assistant.agent import transcript

	for m in tool_messages:
		request = frappe.db.get_value(
			"AI Action Request",
			{
				"conversation": conversation,
				"tool_call_id": m.tool_call_id,
				"status": ["in", ("Approved", "Edited")],
			},
			"name",
		)
		if request:
			status = "Executed" if transcript.tool_status(m) == "ok" else "Failed"
			_set(frappe.get_doc("AI Action Request", request), status=status, result=(m.text or "")[:2000])


def reject_open(conversation: str, reason: str) -> list[dict]:
	"""Mark undecided requests Rejected and return reject decisions for every action of the open interrupt."""
	open_requests = frappe.get_all(
		"AI Action Request",
		filters={"conversation": conversation, "status": "Pending"},
		pluck="name",
	)
	for name in open_requests:
		_set(frappe.get_doc("AI Action Request", name), status="Rejected", decision_message=reason)
	return open_requests


def expire_stale():
	"""Hourly: Pending requests older than the TTL become Expired; their conversation becomes Active."""
	from ai_assistant.services import settings

	minutes = settings.get().action_request_ttl_minutes or 60
	cutoff = add_to_date(now_datetime(), minutes=-minutes)
	stale = frappe.get_all(
		"AI Action Request",
		filters={"status": "Pending", "creation": ["<", cutoff]},
		fields=["name", "conversation"],
	)
	for row in stale:
		_set(frappe.get_doc("AI Action Request", row.name), status="Expired")
		if frappe.db.get_value("AI Conversation", row.conversation, "status") == "Waiting for confirmation":
			conversations.set_status(row.conversation, "Active")


def pending_for(conversation: str) -> list[dict]:
	return frappe.get_all(
		"AI Action Request",
		filters={"conversation": conversation, "status": "Pending"},
		fields=CARD_FIELDS,
		order_by="action_index asc",
	)


def _of_interrupt(conversation: str, interrupt_id: str) -> list:
	return frappe.get_all(
		"AI Action Request",
		filters={"conversation": conversation, "interrupt_id": interrupt_id},
		fields=["name", "status", "tool_name", "edited_args", "decision_message", "result"],
		order_by="action_index asc",
	)


def _set(request, **values):
	if values.get("status") in DECIDED and not request.decided_at:
		values["decided_at"] = now_datetime()
	request.db_set(values)


def _card(doc) -> dict:
	return {f: doc.get(f) for f in CARD_FIELDS}
