"""Conversations and the display transcript (SPEC §4.7, §4.8, §6.5)."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from ai_assistant.services import budget, settings

MAX_TEXT = 20000
BUSY = ("Running", "Waiting for confirmation")


class TurnInProgressError(frappe.ValidationError):
	pass


def load_own(name: str):
	"""The conversation, if it belongs to the session user. Raise PermissionError otherwise."""
	if not name or not frappe.db.exists("AI Conversation", name):
		frappe.throw(_("Conversation not found."), frappe.DoesNotExistError)
	conv = frappe.get_doc("AI Conversation", name)
	conv.check_permission("read")
	if conv.user != frappe.session.user:
		frappe.throw(_("This conversation belongs to another user."), frappe.PermissionError)
	return conv


def get_or_create(name: str | None, context: dict | None = None):
	if name:
		return load_own(name)
	context = context or {}
	doctype = context.get("doctype")
	valid_context = doctype and isinstance(doctype, str) and frappe.db.exists("DocType", doctype)
	return frappe.get_doc(
		{
			"doctype": "AI Conversation",
			"user": frappe.session.user,
			"status": "Active",
			"main_model": settings.get().main_model,
			"context_doctype": doctype if valid_context else None,
			"context_name": (str(context.get("name") or "")[:140] or None) if valid_context else None,
		}
	).insert(ignore_permissions=True)


def start_turn(conv, text: str, attachments: list[str] | None = None, voice_attachment: str | None = None):
	"""Insert the user message and enqueue the turn. One turn per conversation at a time."""
	attachments = _attachments_for(conv, attachments)
	input_mode = "voice" if voice_attachment else "text"
	if voice_attachment:
		from ai_assistant.services import voice

		voice.check_for_message(conv, voice_attachment)
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write a message first."))
	if len(text) > MAX_TEXT:
		frappe.throw(_("The message is too long ({0} characters at most).").format(MAX_TEXT))
	status = frappe.db.get_value("AI Conversation", conv.name, "status", for_update=True)
	if status in BUSY:
		frappe.throw(_("Wait for the current answer, or stop it first."), TurnInProgressError)
	if status == "Archived":
		frappe.throw(_("This conversation is archived. Start a new one."))
	budget.assert_available()
	message = add_message(conv.name, "user", text, input_mode=input_mode, attachments=attachments)
	if attachments:
		from ai_assistant.services import attachments as files

		files.mark_sent(attachments)
	set_status(conv.name, "Running")
	enqueue_turn(conv.name, message=message.name)
	return message


def _attachments_for(conv, names: list[str] | None) -> list[str]:
	if not names:
		return []
	if not settings.get().attachments_enabled:
		frappe.throw(_("Attachments are not enabled."))
	from ai_assistant.services import attachments as files

	return files.for_message(conv, names)


def enqueue_turn(conversation: str, **kwargs):
	frappe.enqueue(
		"ai_assistant.agent.jobs.run_turn",
		queue="long",
		timeout=1800,
		job_id=f"ai-turn-{conversation}",
		deduplicate=True,
		enqueue_after_commit=True,
		now=bool(frappe.in_test),
		conversation=conversation,
		**kwargs,
	)


def add_message(conversation: str, role: str, content: str, **fields):
	idx = frappe.db.count("AI Message", {"conversation": conversation}) + 1
	attachments = [{"attachment": a} for a in fields.pop("attachments", None) or []]
	message = frappe.get_doc(
		{
			"doctype": "AI Message",
			"conversation": conversation,
			"idx_in_thread": idx,
			"role": role,
			"content": content,
			"attachments": attachments,
			**fields,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("AI Conversation", conversation, "last_message_at", now_datetime())
	return message


def set_status(conversation: str, status: str):
	frappe.db.set_value("AI Conversation", conversation, "status", status)


def list_own(limit: int = 20, start: int = 0) -> list[dict]:
	return frappe.get_list(
		"AI Conversation",
		filters={"user": frappe.session.user, "status": ["!=", "Archived"]},
		fields=["name", "title", "status", "last_message_at", "context_doctype", "context_name"],
		order_by="modified desc",
		limit_start=max(int(start), 0),
		limit_page_length=min(max(int(limit), 1), 100),
	)


def payload(conv) -> dict:
	messages = frappe.get_all(
		"AI Message",
		filters={"conversation": conv.name},
		fields=[
			"name",
			"idx_in_thread",
			"role",
			"content",
			"tool_name",
			"tool_status",
			"input_mode",
			"creation",
			"langsmith_run_id",
		],
		order_by="idx_in_thread asc",
	)
	if not frappe.session.user or "System Manager" not in frappe.get_roles():
		for m in messages:
			m.pop("langsmith_run_id", None)
	from ai_assistant.services import actions

	return {
		"conversation": {
			"name": conv.name,
			"title": conv.title,
			"status": conv.status,
			"context_doctype": conv.context_doctype,
			"context_name": conv.context_name,
		},
		"messages": messages,
		"pending_actions": actions.pending_for(conv.name),
	}


def archive(conv):
	if conv.status in BUSY:
		frappe.throw(_("Wait for the current answer, or stop it first."), TurnInProgressError)
	set_status(conv.name, "Archived")
