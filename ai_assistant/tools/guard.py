"""Checks every tool runs first (SPEC §7.2, CLAUDE.md rules 1, 6)."""

import frappe
from frappe import _

from ai_assistant.services import settings

WRITE_PTYPES = ("write", "create", "submit", "cancel", "delete", "email")


class BlockedDocTypeError(frappe.PermissionError):
	pass


def check(doctype: str, ptype: str = "read", name: str | None = None):
	"""Raise unless the session user may `ptype` the DocType (and the document, when named)."""
	require_doctype(doctype)
	if settings.is_blocked(doctype):
		raise BlockedDocTypeError(_("The AI Assistant cannot access {0}.").format(doctype))
	if ptype in WRITE_PTYPES and settings.get().read_only_mode:
		raise frappe.PermissionError(_("The AI Assistant is in read-only mode."))
	if not frappe.has_permission(doctype, ptype, doc=name):
		raise frappe.PermissionError(_("You do not have {0} permission on {1}.").format(_(ptype), doctype))


def require_doctype(doctype: str):
	if not doctype or not isinstance(doctype, str):
		frappe.throw(_("A DocType name is required."))
	try:
		meta = frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		frappe.throw(
			_("DocType {0} does not exist. Use find_doctypes.").format(doctype), frappe.DoesNotExistError
		)
	if meta.istable:
		frappe.throw(_("{0} is a child table. Read it through its parent document.").format(doctype))
