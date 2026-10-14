"""Chat endpoints (SPEC §12). Thin: access check, then services."""

import frappe

from ai_assistant.agent import runner
from ai_assistant.services import access, actions, bootstrap, conversations
from ai_assistant.services import attachments as files


@frappe.whitelist(methods=["POST"])
def send_message(
	text: str,
	conversation: str | None = None,
	context: dict | None = None,
	attachments: list[str] | None = None,
	voice_attachment: str | None = None,
) -> dict:
	access.require_user()
	conv = conversations.get_or_create(conversation, context)
	message = conversations.start_turn(conv, text, attachments=attachments, voice_attachment=voice_attachment)
	return {"conversation": conv.name, "message": message.name}


@frappe.whitelist(methods=["POST"])
def decide_action(
	action_request: str, decision: str, edited_args: dict | None = None, message: str | None = None
) -> dict:
	access.require_user()
	return actions.decide(action_request, decision, edited_args, message)


@frappe.whitelist(methods=["POST"])
def cancel_turn(conversation: str) -> dict:
	access.require_user()
	conv = conversations.load_own(conversation)
	runner.cancel(conv)
	return {"conversation": conv.name}


@frappe.whitelist(methods=["GET"])
def list_conversations(limit: int = 20, start: int = 0) -> list[dict]:
	access.require_user()
	return conversations.list_own(limit, start)


@frappe.whitelist(methods=["GET"])
def get_conversation(conversation: str) -> dict:
	access.require_user()
	return conversations.payload(conversations.load_own(conversation))


@frappe.whitelist(methods=["POST"])
def archive_conversation(conversation: str) -> dict:
	access.require_user()
	conversations.archive(conversations.load_own(conversation))
	return {"conversation": conversation}


@frappe.whitelist(methods=["GET"])
def get_bootstrap() -> dict:
	return bootstrap.get()


@frappe.whitelist(methods=["POST"])
def upload_attachment(conversation: str | None = None) -> dict:
	access.require_user()
	if not frappe.get_cached_doc("AI Assistant Settings").attachments_enabled:
		frappe.throw(frappe._("Attachments are not enabled."))
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(frappe._("No file was uploaded."))
	conv = conversations.get_or_create(conversation)
	att = files.create(conv, upload.filename, upload.stream.read())
	files.enqueue_processing(att.name)
	return {
		"conversation": conv.name,
		"attachment": att.name,
		"status": att.status,
		"file_name": att.file_name,
	}


@frappe.whitelist(methods=["POST"])
def remove_attachment(attachment: str) -> dict:
	access.require_user()
	files.remove(attachment)
	return {"attachment": attachment}
