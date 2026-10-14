"""File tools (SPEC §7.1, §7.2): read_attachment, search_attachments, attach_file."""

import frappe
from frappe import _
from langchain.tools import ToolRuntime, tool

from ai_assistant.agent import context as turn
from ai_assistant.attachments import extractors, upload
from ai_assistant.llm import registry
from ai_assistant.rag.store import FrappeVectorStore
from ai_assistant.services import attachments, conversations, settings
from ai_assistant.tools import base, guard, serialize
from ai_assistant.tools.write import _done, _mark


@tool
def read_attachment(file: str, runtime: ToolRuntime = None) -> dict:
	"""Read the text of a file: a chat attachment of this conversation (by its id) or a File attached to
	a record the user can read (by the File name). Images are not returned; describe what you need instead."""
	return base.execute(
		"read_attachment",
		lambda: _read(file, runtime),
		doctype="File",
		name=file,
		args={"file": file},
		runtime=runtime,
	)


@tool
def search_attachments(query: str, runtime: ToolRuntime = None) -> dict:
	"""Search the large files attached in this conversation for passages about the query."""
	return base.execute(
		"search_attachments", lambda: _search(query, runtime), args={"query": query}, runtime=runtime
	)


@tool
def attach_file(attachment: str, doctype: str, name: str, runtime: ToolRuntime = None) -> dict:
	"""Attach a chat attachment (by its id) to a record as a private file. The user confirms first."""
	return base.execute(
		"attach_file",
		lambda: _attach(attachment, doctype, name, runtime),
		operation="attach",
		doctype=doctype,
		name=name,
		args={"attachment": attachment, "doctype": doctype, "name": name},
		runtime=runtime,
		savepoint=True,
	)


def _read(file: str, runtime) -> dict:
	limit = settings.get().max_attachment_text_chars or 30000
	if attachments.exists(file):
		att = _own_attachment(file, runtime)
		if att.kind == "image":
			return {"file": att.file_name, "kind": "image", "note": _("The image is in the user's message.")}
		return {"file": att.file_name, "kind": att.kind, "text": (att.extracted_text or "")[:limit]}
	doc = frappe.get_doc("File", file)
	doc.check_permission("read")
	if doc.attached_to_doctype and settings.is_blocked(doc.attached_to_doctype):
		raise guard.BlockedDocTypeError(
			_("The AI Assistant cannot access {0}.").format(doc.attached_to_doctype)
		)
	if doc.is_folder or (doc.file_url or "").startswith(("http://", "https://")):
		frappe.throw(_("Only files stored in this system can be read."))
	ext = (doc.file_name or "").rsplit(".", 1)[-1].lower()
	kind = upload.TYPES.get(ext, (None,))[0]
	if kind not in ("pdf", "document", "spreadsheet", "text"):
		frappe.throw(_("Files of type .{0} cannot be read as text.").format(ext))
	content = doc.get_content()
	data = content.encode() if isinstance(content, str) else content
	extracted = extractors.extract(kind, data, doc.file_name)
	return {
		"file": doc.file_name,
		"kind": kind,
		"pages": extracted.page_count,
		"text": extracted.text[:limit],
	}


def _search(query: str, runtime) -> dict:
	ctx = turn.of(runtime)
	if not ctx.conversation:
		frappe.throw(_("There is no conversation to search."))
	conversations.load_own(ctx.conversation)
	store = FrappeVectorStore(registry.get_embeddings(), conversation=ctx.conversation)
	hits = store.similarity_search_with_score(query, k=settings.get().top_k or 6)
	return {
		"query": query,
		"results": [
			{"file": d.metadata.get("title"), "chunk": d.metadata.get("chunk_no"), "text": d.page_content}
			for d, _distance in hits
		],
	}


def _attach(attachment: str, doctype: str, name: str, runtime) -> dict:
	guard.check(doctype, "write", name)
	att = _own_attachment(attachment, runtime)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": att.file_name,
			"content": attachments.read_bytes(att),
			"is_private": 1,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
		}
	).insert()
	_mark(doc, runtime)
	return {
		**_done(doc, "file attached", []),
		"file": file.name,
		"file_link": serialize.desk_link("File", file.name),
	}


def _own_attachment(name: str, runtime):
	att = attachments.load_own(name)
	ctx = turn.of(runtime)
	if ctx.conversation and att.conversation != ctx.conversation:
		frappe.throw(_("This file belongs to another conversation."), frappe.PermissionError)
	return att
