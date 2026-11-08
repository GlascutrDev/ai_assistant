"""Chat endpoints (SPEC §12). Thin: access check, then services."""

import frappe
from frappe.rate_limiter import rate_limit

from ai_assistant.agent import runner
from ai_assistant.services import access, actions, bootstrap, conversations, feedback, voice
from ai_assistant.services import attachments as files


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def send_message(
	text: str,
	conversation: str | None = None,
	context: dict | str | None = None,
	attachments: list[str] | str | None = None,
	voice_attachment: str | None = None,
	agent: str | None = None,
) -> dict:
	access.require_user()
	context = _json_arg(context, dict)
	attachments = _json_arg(attachments, list)
	conv = conversations.get_or_create(conversation, context, agent=agent)
	message = conversations.start_turn(conv, text, attachments=attachments, voice_attachment=voice_attachment)
	return {"conversation": conv.name, "message": message.name}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def decide_action(
	action_request: str, decision: str, edited_args: dict | str | None = None, message: str | None = None
) -> dict:
	access.require_user()
	return actions.decide(action_request, decision, _json_arg(edited_args, dict), message)


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
@rate_limit(limit=60, seconds=60)
def rate_message(message: str | int, rating: str, comment: str | None = None) -> dict:
	access.require_user()
	return feedback.rate(str(message), rating, comment)


@frappe.whitelist(methods=["POST"])
def archive_conversation(conversation: str) -> dict:
	access.require_user()
	conversations.archive(conversations.load_own(conversation))
	return {"conversation": conversation}


@frappe.whitelist(methods=["GET"])
def get_bootstrap() -> dict:
	return bootstrap.get()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def upload_attachment(conversation: str | None = None, agent: str | None = None) -> dict:
	access.require_user()
	if not frappe.get_cached_doc("AI Assistant Settings").attachments_enabled:
		frappe.throw(frappe._("Attachments are not enabled."))
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(frappe._("No file was uploaded."))
	conv = conversations.get_or_create(conversation, agent=agent)
	att = files.create(conv, upload.filename, files.read_upload(upload.stream))
	files.enqueue_processing(att.name)
	return {
		"conversation": conv.name,
		"attachment": att.name,
		"status": att.status,
		"file_name": att.file_name,
	}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=120, seconds=60)
def attachment_status(attachments: list[str] | str) -> list[dict]:
	access.require_user()
	return files.statuses(_json_arg(attachments, list))


@frappe.whitelist(methods=["POST"])
def remove_attachment(attachment: str) -> dict:
	access.require_user()
	files.remove(attachment)
	return {"attachment": attachment}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def transcribe(
	conversation: str | None = None, duration_seconds: float | None = None, agent: str | None = None
) -> dict:
	access.require_user()
	audio = frappe.request.files.get("audio") if frappe.request else None
	if not audio:
		frappe.throw(frappe._("No recording was uploaded."))
	conv = conversations.get_or_create(conversation, agent=agent)
	data = files.read_upload(audio.stream)
	return voice.transcribe(conv, audio.filename or "recording.webm", data, duration_seconds)


def _json_arg(value, expected: type):
	"""frappe.call sends nested objects as JSON strings; accept both forms, reject anything else."""
	if value in (None, ""):
		return None
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except ValueError:
			frappe.throw(frappe._("Invalid JSON argument."))
	if not isinstance(value, expected):
		frappe.throw(frappe._("Expected a {0}.").format(expected.__name__))
	return value
