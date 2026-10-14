"""Cached DocType metadata for find_doctypes. Metadata only; no document data."""

import frappe
from frappe.model import no_value_fields

STANDARD_FIELDS = ("name", "owner", "creation", "modified", "modified_by", "docstatus")
CACHE_KEY = "ai_assistant:doctype_catalog"


def doctypes() -> list[dict]:
	rows = frappe.cache.get_value(CACHE_KEY)
	if rows is None:
		rows = frappe.get_all(
			"DocType",
			filters={"istable": 0},
			fields=["name", "module", "description", "issingle", "is_submittable"],
			order_by="name asc",
		)
		frappe.cache.set_value(CACHE_KEY, rows, expires_in_sec=3600)
	return rows


def is_doctype(name) -> bool:
	return isinstance(name, str) and bool(name) and bool(frappe.db.exists("DocType", name))


def readable_fields(doctype: str, parenttype: str | None = None) -> dict:
	"""Fields the session user may read at their permlevels, minus Password, hidden, and layout fields."""
	meta = frappe.get_meta(doctype)
	permitted = set(meta.get_permitted_fieldnames(parenttype=parenttype, permission_type="read"))
	return {
		df.fieldname: df
		for df in meta.fields
		if df.fieldname in permitted
		and df.fieldtype != "Password"
		and not df.hidden
		and (df.fieldtype not in no_value_fields or df.fieldtype in ("Table", "Table MultiSelect"))
	}


def workflow_states(doctype: str) -> list[dict]:
	from frappe.model.workflow import get_workflow_name

	name = get_workflow_name(doctype)
	if not name:
		return []
	workflow = frappe.get_cached_doc("Workflow", name)
	return [{"state": s.state, "docstatus": s.doc_status} for s in workflow.states]
