import frappe
from frappe import _


class AppendOnlyDocument:
	"""Mixin for rows that are never edited or deleted, except by the retention job (CLAUDE.md rule 12)."""

	def validate(self):
		if not self.is_new() and not frappe.flags.ai_assistant_purge:
			frappe.throw(_("{0} records cannot be changed.").format(_(self.doctype)), frappe.PermissionError)

	def on_trash(self):
		if not frappe.flags.ai_assistant_purge:
			frappe.throw(_("{0} records cannot be deleted.").format(_(self.doctype)), frappe.PermissionError)
