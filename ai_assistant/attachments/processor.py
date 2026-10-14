"""Extract an attachment and choose its delivery: native, text, or indexed (SPEC §6.8)."""

from dataclasses import dataclass

from frappe import _

from ai_assistant.attachments import extractors
from ai_assistant.services import settings

MAX_NATIVE_PDF_PAGES = 100
DISPLAY_CHARS = 30000


@dataclass
class Processed:
	delivery: str
	text: str = ""
	page_count: int | None = None
	duration_seconds: float | None = None
	transcript: str | None = None


def process(
	kind: str, data: bytes, file_name: str, mime_type: str, conversation: str | None = None
) -> Processed:
	main = settings.find_profile(settings.get().main_model)
	if kind == "image":
		return Processed("native")
	if kind in ("audio", "voice"):
		from ai_assistant.llm import speech

		result = speech.transcribe(data, file_name, mime_type, conversation=conversation)
		processed = _text_delivery(result.text)
		processed.duration_seconds = result.duration_seconds
		processed.transcript = result.text
		return processed
	extracted = extractors.extract(kind, data, file_name)
	if kind == "pdf" and main and main.supports_pdf and (extracted.page_count or 0) <= MAX_NATIVE_PDF_PAGES:
		return Processed("native", extracted.text, extracted.page_count)
	processed = _text_delivery(extracted.text)
	processed.page_count = extracted.page_count
	return processed


def _text_delivery(text: str) -> Processed:
	limit = settings.get().max_attachment_text_chars or 30000
	if not text.strip():
		return Processed("text", _("(No text could be read from this file.)"))
	return Processed("indexed" if len(text) > limit else "text", text)


def display_text(text: str) -> str:
	return text[:DISPLAY_CHARS]
