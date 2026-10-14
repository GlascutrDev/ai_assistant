"""Read tools (SPEC §7.1). Every call goes through frappe.get_list / check_permission as the session user."""

import frappe
from frappe import _
from frappe.desk.search import search_widget
from langchain.tools import ToolRuntime, tool

from ai_assistant.services import catalog, settings
from ai_assistant.tools import base, guard, serialize

AGGREGATES = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"}
NUMERIC = ("Int", "Float", "Currency", "Percent", "Duration")
MAX_GROUPS = 200


@tool
def list_documents(
	doctype: str,
	filters: dict | list | None = None,
	fields: list[str] | None = None,
	order_by: str | None = None,
	limit: int = 20,
	offset: int = 0,
	runtime: ToolRuntime = None,
) -> dict:
	"""List records of a DocType that the user can read.

	filters: {"status": "Open"} or {"amount": [">", 100]} or [["status", "in", ["Open", "Overdue"]]].
	fields: field names from describe_doctype (default: name, title, and list-view fields).
	order_by: "<field> asc|desc". The result says when more rows exist than were returned.
	"""
	args = {"doctype": doctype, "filters": filters, "fields": fields, "order_by": order_by, "limit": limit}
	return base.execute(
		"list_documents",
		lambda: _list(doctype, filters, fields, order_by, limit, offset),
		doctype=doctype,
		args=args,
		runtime=runtime,
	)


@tool
def count_documents(doctype: str, filters: dict | list | None = None, runtime: ToolRuntime = None) -> dict:
	"""Count records of a DocType that the user can read, with optional filters (same format as list_documents)."""
	return base.execute(
		"count_documents",
		lambda: {"doctype": doctype, "count": _count(doctype, filters)},
		doctype=doctype,
		args={"doctype": doctype, "filters": filters},
		runtime=runtime,
	)


@tool
def aggregate(
	doctype: str,
	metrics: list[dict],
	group_by: str | None = None,
	filters: dict | list | None = None,
	runtime: ToolRuntime = None,
) -> dict:
	"""Totals over records the user can read.

	metrics: [{"function": "sum" | "avg" | "min" | "max" | "count", "field": "<numeric field>"}]
	(field is ignored for count). group_by: one field name, or none for a grand total.
	"""
	args = {"doctype": doctype, "metrics": metrics, "group_by": group_by, "filters": filters}
	return base.execute(
		"aggregate",
		lambda: _aggregate(doctype, metrics, group_by, filters),
		doctype=doctype,
		args=args,
		runtime=runtime,
	)


@tool
def get_document(doctype: str, name: str, runtime: ToolRuntime = None) -> dict:
	"""Get one record with every field and child-table row the user can read."""
	return base.execute(
		"get_document",
		lambda: _get(doctype, name),
		doctype=doctype,
		name=name,
		args={"doctype": doctype, "name": name},
		runtime=runtime,
	)


@tool
def search_links(doctype: str, text: str, runtime: ToolRuntime = None) -> dict:
	"""Find records of a DocType by name or title text, as the Link field search in Desk does.
	Use it to turn a name the user typed ("acme") into a record name for a filter or a write."""
	return base.execute(
		"search_links",
		lambda: _search(doctype, text),
		doctype=doctype,
		args={"doctype": doctype, "text": text},
		runtime=runtime,
	)


def readable_document(doc) -> dict:
	"""The document's values that the session user may read. Call after check_permission("read")."""
	doc.apply_fieldlevel_read_permissions()
	out = {f: doc.get(f) for f in catalog.STANDARD_FIELDS if doc.get(f) is not None}
	for fieldname, df in catalog.readable_fields(doc.doctype).items():
		if not hasattr(doc, fieldname):
			continue
		if df.fieldtype in ("Table", "Table MultiSelect"):
			child_fields = catalog.readable_fields(df.options, parenttype=doc.doctype)
			out[fieldname] = [
				{f: row.get(f) for f in child_fields if hasattr(row, f) and row.get(f) not in (None, "")}
				for row in doc.get(fieldname) or []
			]
		elif doc.get(fieldname) not in (None, ""):
			out[fieldname] = doc.get(fieldname)
	return out


def _list(doctype, filters, fields, order_by, limit, offset) -> dict:
	guard.check(doctype, "read")
	readable = _allowed_fieldnames(doctype)
	fields = _validate_fields(doctype, fields or _default_fields(doctype), readable)
	_validate_filters(doctype, filters, readable)
	limit = max(1, min(int(limit or 20), settings.max_rows()))
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=fields,
		order_by=_validate_order(order_by, readable),
		limit_start=max(int(offset or 0), 0),
		limit_page_length=limit + 1,
	)
	more = len(rows) > limit
	return {
		"doctype": doctype,
		"rows": rows[:limit],
		"more_rows_exist": more,
		"link": serialize.desk_link(doctype) + "/{name}",
	}


def _count(doctype, filters) -> int:
	guard.check(doctype, "read")
	_validate_filters(doctype, filters, _allowed_fieldnames(doctype))
	rows = frappe.get_list(doctype, filters=filters, fields=[{"COUNT": "*", "as": "count"}])
	return int(rows[0]["count"]) if rows else 0


def _aggregate(doctype, metrics, group_by, filters) -> dict:
	guard.check(doctype, "read")
	readable = _allowed_fieldnames(doctype)
	_validate_filters(doctype, filters, readable)
	numeric = {f for f, df in catalog.readable_fields(doctype).items() if df.fieldtype in NUMERIC}
	fields = []
	for metric in metrics or []:
		function = AGGREGATES.get(str(metric.get("function", "")).lower())
		if not function:
			frappe.throw(
				_("Unknown function {0}. Use sum, avg, min, max, or count.").format(metric.get("function"))
			)
		if function == "COUNT":
			fields.append({"COUNT": "*", "as": "count"})
			continue
		field = metric.get("field")
		if field not in numeric:
			frappe.throw(_("{0} is not a numeric field you can read on {1}.").format(field, doctype))
		fields.append({function: field, "as": f"{function.lower()}_{field}"})
	if not fields:
		frappe.throw(_("Give at least one metric."))
	if group_by:
		if group_by not in readable:
			frappe.throw(_("Unknown field {0} on {1}.").format(group_by, doctype))
		fields.insert(0, group_by)
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=fields,
		group_by=group_by,
		order_by=f"{fields[1]['as']} desc" if group_by else None,
		limit_page_length=MAX_GROUPS + 1 if group_by else 0,
	)
	return {
		"doctype": doctype,
		"group_by": group_by,
		"rows": rows[:MAX_GROUPS],
		"more_groups": len(rows) > MAX_GROUPS,
	}


def _get(doctype, name) -> dict:
	guard.check(doctype, "read", name)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return {
		"doctype": doctype,
		"link": serialize.desk_link(doctype, doc.name),
		"document": readable_document(doc),
	}


def _search(doctype, text) -> dict:
	guard.check(doctype, "read")
	rows = search_widget(doctype, text or "", page_length=20, as_dict=True)
	return {"doctype": doctype, "results": [dict(r) for r in rows or []][:20]}


def _allowed_fieldnames(doctype) -> set[str]:
	return set(catalog.readable_fields(doctype)) | set(catalog.STANDARD_FIELDS)


def _default_fields(doctype) -> list[str]:
	meta = frappe.get_meta(doctype)
	readable = catalog.readable_fields(doctype)
	fields = ["name"]
	if meta.title_field and meta.title_field in readable:
		fields.append(meta.title_field)
	fields += [
		f
		for f, df in readable.items()
		if df.in_list_view and f not in fields and df.fieldtype not in ("Table", "Table MultiSelect")
	]
	return fields[:12]


def _validate_fields(doctype, fields, readable) -> list[str]:
	for field in fields:
		if not isinstance(field, str) or field not in readable:
			frappe.throw(
				_("Unknown or unreadable field {0} on {1}. Use describe_doctype.").format(field, doctype)
			)
	return list(dict.fromkeys(fields))


def _validate_filters(doctype, filters, readable):
	for field, child in _filter_fields(doctype, filters):
		allowed = readable if not child else set(catalog.readable_fields(child, parenttype=doctype))
		if field not in allowed:
			frappe.throw(_("Unknown or unreadable filter field {0}. Use describe_doctype.").format(field))


def _filter_fields(doctype, filters):
	if not filters:
		return
	if isinstance(filters, dict):
		for key in filters:
			yield key, None
		return
	for item in filters:
		if isinstance(item, list | tuple) and len(item) >= 4:
			yield item[1], None if item[0] == doctype else _child_of(doctype, item[0])
		elif isinstance(item, list | tuple) and len(item) >= 2:
			yield item[0], None
		else:
			frappe.throw(_("Filters must be a dict or a list of [field, operator, value]."))


def _child_of(doctype, child) -> str:
	tables = {df.options for df in frappe.get_meta(doctype).get_table_fields()}
	if child not in tables:
		frappe.throw(_("{0} is not a child table of {1}.").format(child, doctype))
	return child


def _validate_order(order_by, readable) -> str | None:
	if not order_by:
		return None
	parts = order_by.strip().split()
	if (
		len(parts) > 2
		or parts[0] not in readable
		or (len(parts) == 2 and parts[1].lower() not in ("asc", "desc"))
	):
		frappe.throw(_("order_by must be '<field> asc' or '<field> desc'."))
	return f"`{parts[0]}` {parts[1] if len(parts) == 2 else 'desc'}"
