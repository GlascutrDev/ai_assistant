"""attachments_inliner: add attachment content to the model request only (SPEC §6.8, CLAUDE.md rule 17)."""

import base64

import frappe
from frappe import _
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import HumanMessage

from ai_assistant.persistence import dblock
from ai_assistant.services import attachments

SUMMARY_CHARS = 2000


@wrap_model_call
def attachments_inliner(request: ModelRequest, handler) -> ModelResponse:
	"""The checkpoint keeps AI Attachment names; this builds content blocks for this call only.
	Only the latest user message gets native image/PDF blocks; older ones get their text."""
	last_human = max((i for i, m in enumerate(request.messages) if isinstance(m, HumanMessage)), default=-1)
	messages, changed = [], False
	for i, message in enumerate(request.messages):
		names = message.additional_kwargs.get("attachments") if isinstance(message, HumanMessage) else None
		if names:
			with dblock.locked():
				message = _inline(message, names, native=i == last_human)
			changed = True
		messages.append(message)
	return handler(request.override(messages=messages) if changed else request)


def _inline(message: HumanMessage, names: list[str], native: bool) -> HumanMessage:
	blocks = [{"type": "text", "text": message.text}]
	for name in names:
		try:
			att = attachments.load_own(name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			frappe.clear_messages()
			continue
		blocks.append(_block(att, native))
	return HumanMessage(content=blocks, id=message.id)


def _block(att, native: bool) -> dict:
	if native and att.delivery == "native" and att.kind in ("image", "pdf"):
		data = base64.b64encode(attachments.read_bytes(att)).decode()
		if att.kind == "image":
			return {"type": "image", "base64": data, "mime_type": att.mime_type}
		return {
			"type": "file",
			"base64": data,
			"mime_type": "application/pdf",
			"extras": {"filename": att.file_name},
		}
	return {"type": "text", "text": _text_block(att)}


def _text_block(att) -> str:
	text = att.extracted_text or ""
	if att.kind == "image":
		text = _("(An image the user sent earlier.)")
	elif att.delivery == "indexed":
		text = (
			text[:SUMMARY_CHARS]
			+ "\n\n"
			+ _("[Only the start of this file is shown. Use search_attachments to find other passages.]")
		)
	pages = f' pages="{att.page_count}"' if att.page_count else ""
	return f'<attachment name="{frappe.utils.escape_html(att.file_name)}" kind="{att.kind}"{pages}>\n{text}\n</attachment>'
