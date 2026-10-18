"""find_doctypes and describe_doctype (SPEC §7.1)."""

import frappe
from frappe.permissions import get_doctypes_with_read
from langchain.tools import ToolRuntime, tool

from ai_assistant.services import catalog, settings
from ai_assistant.tools import base, guard

MAX_RESULTS = 20


@tool
def find_doctypes(query: str = "", runtime: ToolRuntime = None) -> dict:
	"""Find DocTypes (record types such as "Sales Invoice", "ToDo", "Customer") the user can read.

	Search by words in the name, module, or description. Use this before guessing a DocType name.
	"""
	return base.execute("find_doctypes", lambda: _find(query), args={"query": query}, runtime=runtime)


@tool
def describe_doctype(doctype: str, runtime: ToolRuntime = None) -> dict:
	"""Describe a DocType: its fields the user can read (name, label, type, link target, options),
	child tables, whether it is submittable, and its workflow states. Use it before filtering or
	writing, so you use real field names.
	"""
	return base.execute(
		"describe_doctype",
		lambda: _describe(doctype),
		doctype=doctype,
		args={"doctype": doctype},
		runtime=runtime,
	)


def _find(query: str) -> dict:
	readable = set(get_doctypes_with_read())
	words = [w for w in (query or "").lower().split() if w]
	scored = []
	for row in catalog.doctypes():
		if row.name not in readable or settings.is_blocked(row.name):
			continue
		score = _score(row, words)
		if score or not words:
			scored.append((score, row))
	scored.sort(key=lambda item: (-item[0], item[1].name))
	return {
		"doctypes": [
			{
				"doctype": row.name,
				"module": row.module,
				"single": bool(row.issingle),
				"submittable": bool(row.is_submittable),
				"description": (row.description or "")[:200],
			}
			for _, row in scored[:MAX_RESULTS]
		]
	}


def _score(row, words: list[str]) -> int:
	name, module, description = row.name.lower(), (row.module or "").lower(), (row.description or "").lower()
	score = 0
	for word in words:
		score += 5 if word == name else 3 if word in name else 0
		score += 1 if word in module else 0
		score += 1 if word in description else 0
	return score


def _describe(doctype: str) -> dict:
	guard.check(doctype, "read")
	meta = frappe.get_meta(doctype)
	levels = set(meta.get_permlevel_access(permission_type="write"))
	fields, tables = [], []
	for df in catalog.readable_fields(doctype).values():
		if df.fieldtype in ("Table", "Table MultiSelect"):
			child = frappe.get_meta(df.options)
			child_levels = set(child.get_permlevel_access(permission_type="write", parenttype=doctype))
			tables.append(
				{
					"fieldname": df.fieldname,
					"label": df.label,
					"child_doctype": df.options,
					"fields": [
						_field(c, child_levels)
						for c in catalog.readable_fields(df.options, parenttype=doctype).values()
					],
				}
			)
		else:
			fields.append(_field(df, levels))
	return {
		"doctype": doctype,
		"single": bool(meta.issingle),
		"submittable": bool(meta.is_submittable),
		"title_field": meta.title_field,
		"standard_fields": list(catalog.STANDARD_FIELDS),
		"fields": fields,
		"child_tables": tables,
		"workflow_states": catalog.workflow_states(doctype),
	}


def _field(df, write_levels: set[int]) -> dict:
	out = {"fieldname": df.fieldname, "label": df.label, "type": df.fieldtype}
	if df.fieldtype == "Link":
		out["link_to"] = "(restricted)" if settings.is_blocked(df.options) else df.options
	elif df.fieldtype == "Select" and df.options:
		out["options"] = [o for o in df.options.split("\n") if o][:50]
	elif df.fieldtype == "Dynamic Link":
		out["link_to_field"] = df.options
	if df.reqd:
		out["required"] = True
	if df.read_only or df.permlevel not in write_levels:
		out["read_only"] = True
	return out
