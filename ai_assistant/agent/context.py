from dataclasses import dataclass, field

import frappe


@dataclass
class TurnContext:
	"""Per-turn context passed as `context=` to the graph. Permissions come from the session user, not `user`."""

	user: str
	conversation: str | None = None
	lang: str = "en"
	model_profile: str | None = None
	is_evaluation: bool = False
	desk_context: dict | None = None
	limits: dict = field(default_factory=dict)


def of(runtime=None) -> TurnContext:
	"""The turn context of a tool call; a session-only context when a tool is called directly."""
	context = getattr(runtime, "context", None)
	if context is not None:
		if context.user != frappe.session.user:
			frappe.throw("Turn context user does not match the session user.", frappe.PermissionError)
		return context
	return TurnContext(user=frappe.session.user, lang=frappe.local.lang or "en")
