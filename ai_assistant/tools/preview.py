"""Confirmation card content and pre-checks for write tools (SPEC §7.2, §7.4)."""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import escape_html, strip_html

from ai_assistant import tools
from ai_assistant.services import catalog
from ai_assistant.tools import guard

PTYPES = {
	"create_document": "create",
	"update_document": "write",
	"submit_document": "submit",
	"cancel_document": "cancel",
	"delete_document": "delete",
	"add_comment": "read",
	"assign_to": "read",
	"apply_workflow_action": "read",
	"attach_file": "write",
}


def spec_of(tool_name: str) -> dict | None:
	"""Card spec of a write tool with its own pre-check and preview (a core tool here, or an extension).
	A core spec's `precheck` runs every guard check itself (`own_guard`)."""
	from ai_assistant.tools import bulk, mail, spreadsheets
	from ai_assistant.tools import memory as memory_tools

	bulk_spec = {"own_guard": True, "precheck": bulk.precheck, "preview": bulk.preview_rows, "by_name": True}
	core = {
		"write_spreadsheet": {
			"operation": "create",
			"doctype": "File",
			"own_guard": True,
			"precheck": spreadsheets.precheck,
			"preview": spreadsheets.preview_rows,
		},
		"create_documents": {**bulk_spec, "operation": "create"},
		"update_documents": {**bulk_spec, "operation": "update"},
		"delete_documents": {**bulk_spec, "operation": "delete"},
		"send_email": {"operation": "email", "own_guard": True, "precheck": mail.precheck},
	}
	memory_spec = {
		"doctype": "AI Memory",
		"own_guard": True,
		"by_name": True,
		"precheck": memory_tools.precheck,
		"preview": memory_tools.preview_rows,
	}
	core["remember"] = {**memory_spec, "operation": "create"}
	core["forget_memory"] = {**memory_spec, "operation": "delete"}
	return core.get(tool_name) or tools.write_spec(tool_name)


def target_of(tool_name: str, args: dict) -> tuple[str | None, str | None]:
	if tool_name == "send_email":
		doctype = args.get("reference_doctype")
		return (
			(doctype, args.get("reference_name")) if catalog.is_doctype(doctype) else ("Communication", None)
		)
	if spec := spec_of(tool_name):
		doctype = spec.get("doctype") or args.get("doctype")
		return (doctype if catalog.is_doctype(doctype) else None), None
	doctype = args.get("doctype")
	name = args.get("name")
	doctype = doctype if catalog.is_doctype(doctype) else None
	return doctype, (str(name)[:140] if name else None)


def precheck(tool_name: str, args: dict) -> str | None:
	"""Error message when the write would fail on access or field names, else None."""
	try:
		if spec := spec_of(tool_name):
			_extension_precheck(tool_name, spec, args)
		else:
			_core_precheck(tool_name, args)
	except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError) as e:
		frappe.clear_messages()
		return strip_html(str(e)) or _("Permission denied.")
	return None


def _core_precheck(tool_name: str, args: dict):
	doctype, name = args.get("doctype"), args.get("name")
	guard.check(doctype, PTYPES.get(tool_name, "write"), name if tool_name != "create_document" else None)
	if tool_name in ("create_document", "update_document"):
		check_values(doctype, args.get("values") or {}, new=tool_name == "create_document")


def _extension_precheck(tool_name: str, spec: dict, args: dict):
	if not spec.get("own_guard"):
		guard.check(spec["doctype"], "write" if spec["operation"] == "update" else spec["operation"])
	if spec.get("precheck"):
		_call(spec, "precheck", tool_name, args)


def _call(spec: dict, key: str, tool_name: str, args: dict):
	return spec[key](tool_name, args) if spec.get("by_name") else spec[key](args)


def check_values(doctype: str, values: dict, new: bool):
	"""Values may set only fields the user can write at their permlevels."""
	if not isinstance(values, dict) or not values:
		frappe.throw(_("Give the field values as an object."))
	meta = frappe.get_meta(doctype)
	levels = set(meta.get_permlevel_access(permission_type="write"))
	for field in values:
		df = meta.get_field(field)
		is_value = df and (df.fieldtype not in no_value_fields or df.fieldtype in table_fields)
		if not is_value or df.permlevel not in levels:
			frappe.throw(_("Field {0} does not exist on {1} or you cannot write it.").format(field, doctype))
		if df.fieldtype == "Password":
			frappe.throw(_("The AI Assistant cannot set passwords."))
		if not new and (df.read_only or df.set_only_once):
			frappe.throw(_("Field {0} cannot be changed.").format(field))
		if df.fieldtype in table_fields:
			_check_rows(doctype, df, values[field])


def _check_rows(doctype: str, df, rows):
	"""Child rows may set only the child DocType's fields the user can write; no name, parent, or docstatus."""
	if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
		frappe.throw(_("{0} must be a list of rows.").format(df.fieldname))
	child = frappe.get_meta(df.options)
	levels = set(child.get_permlevel_access(permission_type="write", parenttype=doctype))
	for row in rows:
		for field in row:
			child_df = child.get_field(field)
			if not child_df or child_df.fieldtype in no_value_fields or child_df.permlevel not in levels:
				frappe.throw(
					_("Field {0} does not exist on {1} or you cannot write it.").format(field, df.options)
				)


def preview_html(tool_name: str, args: dict) -> str:
	"""The actual arguments, and for updates the current values next to the new ones. An extension write
	tool's `preview(args)` gives (headers, rows); the cells are escaped here like every other card."""
	if (spec := spec_of(tool_name)) and spec.get("preview"):
		try:
			headers, rows = _call(spec, "preview", tool_name, args)
		except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
			frappe.clear_messages()
		else:
			return _table(headers, rows)
	if tool_name == "update_document" and isinstance(args.get("values"), dict):
		return _diff(args["doctype"], args.get("name"), args["values"])
	if tool_name == "create_document" and isinstance(args.get("values"), dict):
		return _table(["Field", "Value"], [(k, v) for k, v in args["values"].items()])
	return _table(["Argument", "Value"], [(k, v) for k, v in args.items()])


def _diff(doctype: str, name: str, values: dict) -> str:
	current = {}
	try:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
		current = {k: doc.get(k) for k in values}
	except Exception:
		frappe.clear_messages()
	return _table(["Field", "Now", "New"], [(k, current.get(k), v) for k, v in values.items()])


def _table(headers: list[str], rows: list[tuple]) -> str:
	head = "".join(f"<th>{escape_html(_(h))}</th>" for h in headers)
	body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row) + "</tr>" for row in rows)
	return f'<table class="table table-bordered table-sm"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _cell(value) -> str:
	text = value if isinstance(value, str) else frappe.as_json(value, indent=None)
	return escape_html(str(text)[:500])
