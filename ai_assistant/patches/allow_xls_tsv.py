import frappe

NEW_TYPES = ("xls", "tsv")


def execute():
	"""Add the spreadsheet types of SPEC §6.8.1 to a site's stored allow-list; never remove one."""
	current = frappe.db.get_single_value("AI Assistant Settings", "allowed_file_types") or ""
	types = current.split()
	if not types or "xlsx" not in types:
		return
	added = [t for t in NEW_TYPES if t not in types]
	if added:
		frappe.db.set_single_value("AI Assistant Settings", "allowed_file_types", "\n".join(types + added))
