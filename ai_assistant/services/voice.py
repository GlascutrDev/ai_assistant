"""Voice prompts (SPEC §6.7): the recording is transcribed first; the agent receives text only."""

import frappe
from frappe import _

from ai_assistant.services import attachments


def check_for_message(conv, name: str):
	"""A voice recording sent with a message: this user's, this conversation's, transcribed, unsent."""
	att = attachments.load_own(name)
	if att.conversation != conv.name or att.kind != "voice":
		frappe.throw(_("This recording belongs to another conversation."), frappe.PermissionError)
	if att.status != "Ready" or att.sent:
		frappe.throw(_("This recording cannot be sent."))
	frappe.db.set_value("AI Attachment", att.name, "sent", 1)


def transcribe(conv, file_name: str, data: bytes, duration_seconds: float | None = None) -> dict:
	"""Store the recording as a private File + AI Attachment (voice) and transcribe it synchronously."""
	from ai_assistant.llm import speech
	from ai_assistant.services import settings

	conf = settings.get()
	if not conf.voice_enabled:
		frappe.throw(_("Voice prompts are not enabled."))
	limit = conf.max_voice_seconds or 120
	measured = speech.audio_duration(data) or float(duration_seconds or 0)
	if measured > limit + 1:
		frappe.throw(_("The recording is longer than {0} seconds.").format(limit))
	att = attachments.create(conv, file_name, data, voice=True)
	result = speech.transcribe(data, att.file_name, att.mime_type, conv.name, duration_seconds=measured)
	att.db_set(
		{
			"status": "Ready",
			"delivery": "text",
			"transcript": result.text,
			"extracted_text": result.text,
			"duration_seconds": result.duration_seconds,
		}
	)
	return {
		"conversation": conv.name,
		"attachment": att.name,
		"text": result.text,
		"language": result.language,
		"duration_seconds": result.duration_seconds,
	}
