"""Speech-to-text with the speech model from Settings (SPEC §6.7). One of the places API keys are read."""

import base64
import io
import wave
from dataclasses import dataclass

import frappe
from frappe import _

from ai_assistant.llm import registry, usage
from ai_assistant.services import settings

GEMINI_INSTRUCTION = "Transcribe this audio verbatim. Output only the transcript, nothing else."


@dataclass
class Transcript:
	text: str
	language: str | None
	duration_seconds: float


def transcribe(
	data: bytes,
	file_name: str,
	mime_type: str,
	conversation: str | None = None,
	duration_seconds: float | None = None,
) -> Transcript:
	profile, credential = resolve()
	language = (frappe.local.lang or "en").split("-")[0].lower()
	duration = audio_duration(data) or float(duration_seconds or 0)
	try:
		text = _transcribe(profile, credential, data, file_name, mime_type, language)
	except Exception as e:
		frappe.log_error("AI Assistant transcription failed")
		frappe.throw(_("Transcription failed: {0}").format(registry.redact(str(e)[:300], credential)))
	usage.record(
		profile_id=profile.profile_id,
		purpose="transcription",
		audio_seconds=duration,
		conversation=conversation,
	)
	return Transcript(text=(text or "").strip(), language=language, duration_seconds=duration)


def resolve():
	return registry.resolve(settings.get().speech_model, "Speech-to-text")


def audio_duration(data: bytes) -> float | None:
	"""Server-side length of WAV audio; other formats rely on the recorder's timer."""
	try:
		with wave.open(io.BytesIO(data)) as w:
			return w.getnframes() / float(w.getframerate())
	except (wave.Error, EOFError, ZeroDivisionError):
		return None


def _transcribe(profile, credential, data, file_name, mime_type, language) -> str:
	if credential.provider == "Google Gemini":
		return _gemini(profile, credential, data, mime_type)
	if credential.provider not in ("OpenAI", "OpenAI Compatible"):
		frappe.throw(_("Provider {0} does not support speech-to-text.").format(credential.provider))
	from openai import OpenAI

	client = OpenAI(
		api_key=registry.api_key(credential) or "none",
		base_url=credential.base_url or None,
		timeout=profile.timeout_seconds or 120,
	)
	result = client.audio.transcriptions.create(
		file=(file_name, data, mime_type), model=profile.model_name, language=language
	)
	return result.text


def _gemini(profile, credential, data, mime_type) -> str:
	from langchain_core.messages import HumanMessage

	model = registry._build_chat(profile, credential)
	reply = model.invoke(
		[
			HumanMessage(
				content=[
					{"type": "text", "text": GEMINI_INSTRUCTION},
					{"type": "audio", "base64": base64.b64encode(data).decode(), "mime_type": mime_type},
				]
			)
		]
	)
	return reply.text
