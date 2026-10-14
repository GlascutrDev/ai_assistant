"""Write tools (SPEC §7.2). Each is interrupted for confirmation; the body runs only after approval."""

import frappe
from frappe import _
from frappe.desk.form import assign_to as assign
from frappe.model.workflow import apply_workflow
from langchain.tools import ToolRuntime, tool

from ai_assistant.agent import context as turn
from ai_assistant.tools import base, guard, serialize
from ai_assistant.tools.preview import check_values


@tool
def create_document(doctype: str, values: dict, runtime: ToolRuntime = None) -> dict:
	"""Create a record. values: {fieldname: value}; child tables as lists of row dicts.
	The user confirms before it is created."""
	return _run(
		"create_document",
		doctype,
		None,
		{"values": values},
		lambda: _create(doctype, values, runtime),
		runtime,
	)


@tool
def update_document(doctype: str, name: str, values: dict, runtime: ToolRuntime = None) -> dict:
	"""Change fields of a record. values: only the fields to change. The user confirms first."""
	return _run(
		"update_document",
		doctype,
		name,
		{"values": values},
		lambda: _update(doctype, name, values, runtime),
		runtime,
	)


@tool
def submit_document(doctype: str, name: str, runtime: ToolRuntime = None) -> dict:
	"""Submit a draft of a submittable DocType. The user confirms first."""
	return _run(
		"submit_document", doctype, name, {}, lambda: _lifecycle(doctype, name, "submit", runtime), runtime
	)


@tool
def cancel_document(doctype: str, name: str, runtime: ToolRuntime = None) -> dict:
	"""Cancel a submitted record. The user confirms first."""
	return _run(
		"cancel_document", doctype, name, {}, lambda: _lifecycle(doctype, name, "cancel", runtime), runtime
	)


@tool
def delete_document(doctype: str, name: str, runtime: ToolRuntime = None) -> dict:
	"""Delete a record. The user confirms first."""
	return _run("delete_document", doctype, name, {}, lambda: _delete(doctype, name), runtime)


@tool
def add_comment(doctype: str, name: str, text: str, runtime: ToolRuntime = None) -> dict:
	"""Add a comment to a record's timeline. The user confirms first."""
	return _run(
		"add_comment", doctype, name, {"text": text}, lambda: _comment(doctype, name, text, runtime), runtime
	)


@tool
def assign_to(
	doctype: str,
	name: str,
	users: list[str],
	description: str | None = None,
	date: str | None = None,
	runtime: ToolRuntime = None,
) -> dict:
	"""Assign a record to users (creates ToDos). date: YYYY-MM-DD due date. The user confirms first."""
	args = {"users": users, "description": description, "date": date}
	return _run(
		"assign_to",
		doctype,
		name,
		args,
		lambda: _assign(doctype, name, users, description, date, runtime),
		runtime,
	)


@tool
def apply_workflow_action(doctype: str, name: str, action: str, runtime: ToolRuntime = None) -> dict:
	"""Apply a workflow action (e.g. "Approve") to a record. The user confirms first."""
	return _run(
		"apply_workflow_action",
		doctype,
		name,
		{"action": action},
		lambda: _workflow(doctype, name, action, runtime),
		runtime,
	)


def _run(tool_name, doctype, name, extra, body, runtime) -> dict:
	from ai_assistant.services.actions import OPERATIONS

	return base.execute(
		tool_name,
		body,
		operation=OPERATIONS[tool_name],
		doctype=doctype,
		name=name,
		args={"doctype": doctype, "name": name, **extra},
		runtime=runtime,
		savepoint=True,
	)


def _create(doctype, values, runtime) -> dict:
	guard.check(doctype, "create")
	check_values(doctype, values, new=True)
	doc = frappe.get_doc({**values, "doctype": doctype}).insert()
	_mark(doc, runtime)
	return _done(doc, "created", list(values))


def _update(doctype, name, values, runtime) -> dict:
	guard.check(doctype, "write", name)
	check_values(doctype, values, new=False)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	doc.update(values)
	doc.save()
	_mark(doc, runtime)
	return _done(doc, "updated", list(values))


def _lifecycle(doctype, name, action, runtime) -> dict:
	guard.check(doctype, action, name)
	doc = frappe.get_doc(doctype, name)
	getattr(doc, action)()
	_mark(doc, runtime)
	return _done(doc, f"{action}ted" if action == "submit" else "cancelled", ["docstatus"])


def _delete(doctype, name) -> dict:
	guard.check(doctype, "delete", name)
	frappe.delete_doc(doctype, name)
	return {"doctype": doctype, "name": name, "result": "deleted"}


def _comment(doctype, name, text, runtime) -> dict:
	guard.check(doctype, "read", name)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	comment = doc.add_comment("Comment", frappe.utils.escape_html(text))
	_mark(doc, runtime)
	return {"doctype": doctype, "name": name, "result": "commented", "comment": comment.name}


def _assign(doctype, name, users, description, date, runtime) -> dict:
	guard.check(doctype, "read", name)
	if not users or not isinstance(users, list):
		frappe.throw(_("Give at least one user."))
	assign.add(
		{"assign_to": users, "doctype": doctype, "name": name, "description": description, "date": date}
	)
	_mark(frappe.get_doc(doctype, name), runtime)
	return {"doctype": doctype, "name": name, "result": "assigned", "users": users}


def _workflow(doctype, name, action, runtime) -> dict:
	guard.check(doctype, "read", name)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc = apply_workflow(doc, action)
	_mark(doc, runtime)
	return _done(doc, f"workflow action {action} applied", ["workflow_state"])


def _done(doc, result: str, changed: list) -> dict:
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"link": serialize.desk_link(doc.doctype, doc.name),
		"result": result,
		"changed_fields": changed,
	}


def _mark(doc, runtime):
	"""Timeline note on the target (SPEC §10)."""
	ctx = turn.of(runtime)
	link = (
		f'<a href="{serialize.desk_link("AI Conversation", ctx.conversation)}">{ctx.conversation}</a>'
		if ctx.conversation
		else ""
	)
	user = frappe.utils.get_fullname(frappe.session.user)
	doc.add_comment("Info", _("Done by AI Assistant for {0} (conversation {1})").format(user, link or "-"))
