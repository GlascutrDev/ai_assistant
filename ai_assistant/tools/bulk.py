"""Bulk write tools (SPEC §7.2): many records of one DocType in one confirmed action, all or nothing."""

import frappe
from frappe import _
from frappe.model import table_fields
from langchain.tools import ToolRuntime, tool

from ai_assistant.tools import base, guard
from ai_assistant.tools.preview import check_values
from ai_assistant.tools.write import _mark

MAX_RECORDS = 50


@tool
def create_documents(doctype: str, records: list[dict], runtime: ToolRuntime = None) -> dict:
	"""Create several records of one DocType at once (at most 50). records: a list of {fieldname: value};
	child tables as lists of row dicts. All are created, or none if one fails. The user confirms first."""
	args = {"doctype": doctype, "records": records}
	return _run("create_documents", doctype, args, lambda: _create(doctype, records, runtime), runtime)


@tool
def update_documents(doctype: str, names: list[str], values: dict, runtime: ToolRuntime = None) -> dict:
	"""Set the same field values on several records of one DocType (at most 50). All are changed, or none
	if one fails. The user confirms first."""
	args = {"doctype": doctype, "names": names, "values": values}
	return _run("update_documents", doctype, args, lambda: _update(doctype, names, values, runtime), runtime)


@tool
def delete_documents(doctype: str, names: list[str], runtime: ToolRuntime = None) -> dict:
	"""Delete several records of one DocType (at most 50). All are deleted, or none if one fails (for
	example because another record links to it). The user confirms first."""
	args = {"doctype": doctype, "names": names}
	return _run("delete_documents", doctype, args, lambda: _delete(doctype, names), runtime)


def precheck(tool_name: str, args: dict):
	"""See ai_assistant.tools.preview.precheck."""
	doctype = args.get("doctype")
	if tool_name == "create_documents":
		guard.check(doctype, "create")
		for values in _records(args.get("records")):
			check_values(doctype, values, new=True)
		return
	names = _names(args.get("names"))
	ptype = "write" if tool_name == "update_documents" else "delete"
	if tool_name == "update_documents":
		check_values(doctype, args.get("values") or {}, new=False)
	for name in names:
		guard.check(doctype, ptype, name)


def preview_rows(tool_name: str, args: dict) -> tuple[list[str], list[tuple]]:
	if tool_name == "create_documents":
		records = _records(args.get("records"))
		fields = list(dict.fromkeys(k for r in records for k in r))
		return ["#", *fields], [(i, *(r.get(f) for f in fields)) for i, r in enumerate(records, 1)]
	names = _names(args.get("names"))
	if tool_name == "delete_documents":
		return ["Delete"], [(n,) for n in names]
	values = args.get("values") or {}
	meta = frappe.get_meta(args["doctype"])
	plain = [f for f in values if (df := meta.get_field(f)) and df.fieldtype not in table_fields]
	current = {
		r.name: r
		for r in frappe.get_list(
			args["doctype"], filters={"name": ["in", names]}, fields=["name", *plain], limit=MAX_RECORDS
		)
	}
	rows = [(n, f, (current.get(n) or {}).get(f), v) for n in names for f, v in values.items()]
	return ["Record", "Field", "Now", "New"], rows


def _run(tool_name, doctype, args, body, runtime) -> dict:
	from ai_assistant.services.actions import OPERATIONS

	return base.execute(
		tool_name,
		body,
		operation=OPERATIONS[tool_name],
		doctype=doctype,
		args=args,
		runtime=runtime,
		savepoint=True,
	)


def _create(doctype, records, runtime) -> dict:
	guard.check(doctype, "create")
	created = []
	for values in _records(records):
		check_values(doctype, values, new=True)
		doc = frappe.get_doc({**values, "doctype": doctype}).insert()
		_mark(doc, runtime)
		created.append(doc.name)
	return {"doctype": doctype, "result": "created", "names": created}


def _update(doctype, names, values, runtime) -> dict:
	check_values(doctype, values, new=False)
	for name in _names(names):
		guard.check(doctype, "write", name)
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		doc.update(values)
		doc.save()
		_mark(doc, runtime)
	return {"doctype": doctype, "result": "updated", "names": names, "changed_fields": list(values)}


def _delete(doctype, names) -> dict:
	for name in _names(names):
		guard.check(doctype, "delete", name)
		frappe.delete_doc(doctype, name)
	return {"doctype": doctype, "result": "deleted", "names": names}


def _records(records) -> list[dict]:
	if not isinstance(records, list) or not records or not all(isinstance(r, dict) for r in records):
		frappe.throw(_("Give records as a list of field-value objects."))
	return _limit(records)


def _names(names) -> list[str]:
	if not isinstance(names, list) or not names or not all(isinstance(n, str | int) for n in names):
		frappe.throw(_("Give names as a list of record names."))
	return _limit([str(n) for n in dict.fromkeys(names)])


def _limit(items: list) -> list:
	if len(items) > MAX_RECORDS:
		frappe.throw(_("At most {0} records at a time.").format(MAX_RECORDS))
	return items
