"""AI Feedback: a user's thumbs up or down on one assistant answer (SPEC §6.9)."""

import frappe
from frappe import _

from ai_assistant.services import conversations, memory

DOCTYPE = "AI Feedback"
MAX_COMMENT = 1000


def rate(message: str, rating: str, comment: str | None = None) -> dict:
	"""One rating per answer and user; rating again replaces it. A Down comment becomes a personal memory."""
	if rating not in ("Up", "Down"):
		frappe.throw(_("Rating must be Up or Down."))
	msg = frappe.db.get_value("AI Message", message, ["conversation", "role", "model"], as_dict=True)
	if not msg or msg.role != "assistant":
		frappe.throw(_("Only an assistant answer can be rated."), frappe.DoesNotExistError)
	conversations.load_own(msg.conversation)
	comment = (comment or "").strip()[:MAX_COMMENT] or None
	values = {"rating": rating, "comment": comment, "model": msg.model, "conversation": msg.conversation}
	name = frappe.db.get_value(DOCTYPE, {"message": message, "user": frappe.session.user})
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{"doctype": DOCTYPE, "message": message, "user": frappe.session.user, **values}
		).insert(ignore_permissions=True)
	saved = memory.from_feedback(comment, msg.conversation) if rating == "Down" and comment else None
	return {"feedback": doc.name, "rating": rating, "memory": saved}


def ratings_for(conversation: str) -> dict[str, str]:
	"""{message: rating} of the session user in a conversation, for the chat UI."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"conversation": conversation, "user": frappe.session.user},
		fields=["message", "rating"],
	)
	return {str(r.message): r.rating for r in rows}
