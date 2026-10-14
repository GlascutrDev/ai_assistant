import frappe
from frappe import _

from ai_assistant.services import settings


class AssistantDisabledError(frappe.ValidationError):
	pass


def has_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Guest":
		return False
	roles = set(frappe.get_roles(user))
	if roles & {"System Manager", settings.ASSISTANT_ROLE}:
		return True
	allowed = {row.role for row in settings.get().allowed_roles}
	return bool(roles & allowed)


def require_user() -> str:
	"""Check Guest, `enabled`, and access for the session user. Return the user."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please log in to use the AI Assistant."), frappe.PermissionError)
	if not settings.get().enabled:
		frappe.throw(_("AI Assistant is disabled."), AssistantDisabledError)
	if not has_access(user):
		frappe.throw(_("You do not have access to the AI Assistant."), frappe.PermissionError)
	return user


def is_admin(user: str | None = None) -> bool:
	return "System Manager" in frappe.get_roles(user or frappe.session.user)
