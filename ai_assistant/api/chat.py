"""Chat endpoints (SPEC §12). Thin: access check, then services."""

import frappe

from ai_assistant.agent import runner
from ai_assistant.services import access, actions, bootstrap, conversations


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
	runner.request_cancel(conv.name)
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
