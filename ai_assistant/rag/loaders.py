"""Text of a source document for indexing (SPEC §8.1, §8.2)."""

import json

import frappe
from frappe.utils import strip_html

TEXT_TYPES = (
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Text Editor",
	"Markdown Editor",
	"HTML Editor",
	"Select",
	"Link",
	"Read Only",
)
KNOWLEDGE_DOCTYPE = "AI Knowledge Document"


def text_of(doc, content_fields: str | None = None) -> str:
	"""Title, then each content field as "Label: value"."""
	if doc.doctype == KNOWLEDGE_DOCTYPE:
		return knowledge_text(doc)
	meta = frappe.get_meta(doc.doctype)
	wanted = [f.strip() for f in (content_fields or "").splitlines() if f.strip()]
	fields = (
		[meta.get_field(f) for f in wanted]
		if wanted
		else [df for df in meta.fields if df.fieldtype in TEXT_TYPES]
	)
	parts = [f"{doc.doctype}: {title_of(doc)}"]
	for df in fields:
		if not df or df.fieldtype == "Password" or df.hidden:
			continue
		value = doc.get(df.fieldname)
		if value not in (None, ""):
			parts.append(f"{df.label or df.fieldname}: {strip_html(str(value)).strip()}")
	return "\n".join(parts)


def knowledge_text(doc) -> str:
	parts = [doc.title, strip_html(doc.content or "").strip()]
	if doc.attachment:
		parts.append(file_text(doc.attachment))
	return "\n\n".join(p for p in parts if p)


def file_text(file_url: str) -> str:
	"""Text of a knowledge document's attachment (PDF, DOCX, TXT, MD). Indexer only: not user-facing."""
	from ai_assistant.attachments import extractors

	file = frappe.get_doc("File", {"file_url": file_url})
	name = (file.file_name or "").lower()
	content = file.get_content()
	if isinstance(content, str):
		content = content.encode()
	kind = "pdf" if name.endswith(".pdf") else "document" if name.endswith(".docx") else "text"
	return extractors.extract(kind, content).text


def title_of(doc) -> str:
	meta = frappe.get_meta(doc.doctype)
	return str(doc.get(meta.title_field) or doc.name) if meta.title_field else str(doc.name)


def matches_filters(doctype: str, name: str, filters_json: str | None) -> bool:
	if not filters_json:
		return True
	filters = json.loads(filters_json)
	return bool(frappe.get_all(doctype, filters={**filters, "name": name}, limit=1))
