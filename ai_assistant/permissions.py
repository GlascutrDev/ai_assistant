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


def memory_has_permission(doc, ptype=None, user=None) -> bool:
	"""Shared memories: read for assistant users, write for System Managers. Personal: their user only."""
	user = user or frappe.session.user
	if is_admin(user):
		return True
	if doc.scope == "Shared":
		return ptype in (None, "read") and has_access(user)
	return (doc.user or user) == user and has_access(user)


def memory_query(user=None) -> str:
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	return f"(`tabAI Memory`.user = {frappe.db.escape(user)} or `tabAI Memory`.scope = 'Shared')"


def automation_has_permission(doc, ptype=None, user=None) -> bool:
	"""Owner only; a new automation is the session user's."""
	user = user or frappe.session.user
	if is_admin(user):
		return True
	return (doc.user or user) == user and has_access(user)


def automation_query(user=None) -> str:
	return _owner_condition("AI Automation", user)


def agent_has_permission(doc, ptype=None, user=None) -> bool:
	"""System Managers manage agents; other users read the ones they can use."""
	from ai_assistant.services import agents

	user = user or frappe.session.user
	if is_admin(user):
		return True
	return ptype in (None, "read") and agents.can_use(doc, user)


def agent_query(user=None) -> str:
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	roles = ", ".join(frappe.db.escape(r) for r in frappe.get_roles(user)) or "''"
	limited = "select parent from `tabAI Allowed Role` where parenttype = 'AI Agent'"
	mine = f"{limited} and role in ({roles})"
	return f"`tabAI Agent`.enabled = 1 and (`tabAI Agent`.name not in ({limited}) or `tabAI Agent`.name in ({mine}))"


def feedback_query(user=None) -> str:
	return _owner_condition("AI Feedback", user)


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
