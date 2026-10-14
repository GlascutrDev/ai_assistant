"""Owner-only access to per-user AI records. Hooks can only deny; role permissions grant read."""

import frappe

from ai_assistant.services.access import has_access, is_admin


def conversation_has_permission(doc, ptype=None, user=None) -> bool:
	user = user or frappe.session.user
	if is_admin(user):
		return True
	return doc.user == user and has_access(user)


def owned_record_has_permission(doc, ptype=None, user=None) -> bool:
	"""AI Attachment, AI Action Request, AI Usage Log: rows with a `user` field."""
	user = user or frappe.session.user
	if is_admin(user):
		return True
	return doc.user == user and has_access(user)


def message_has_permission(doc, ptype=None, user=None) -> bool:
	user = user or frappe.session.user
	if is_admin(user):
		return True
	owner = frappe.db.get_value("AI Conversation", doc.conversation, "user")
	return owner == user and has_access(user)


def conversation_query(user=None) -> str:
	return _owner_condition("AI Conversation", user)


def attachment_query(user=None) -> str:
	return _owner_condition("AI Attachment", user)


def action_request_query(user=None) -> str:
	return _owner_condition("AI Action Request", user)


def usage_log_query(user=None) -> str:
	return _owner_condition("AI Usage Log", user)


def message_query(user=None) -> str:
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	return (
		"`tabAI Message`.conversation in "
		f"(select name from `tabAI Conversation` where user = {frappe.db.escape(user)})"
	)


def _owner_condition(doctype: str, user: str | None) -> str:
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	return f"`tab{doctype}`.user = {frappe.db.escape(user)}"
