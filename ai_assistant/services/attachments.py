"""AI Attachment lifecycle: upload, process, send, remove, purge (SPEC §4.14, §6.8)."""

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from ai_assistant.attachments import processor, upload
from ai_assistant.persistence import schema
from ai_assistant.persistence.schema import EMBEDDING_TABLE
from ai_assistant.services import settings

SOURCE = "AI Attachment"


def create(conv, file_name: str, data: bytes, voice: bool = False):
	"""Check the upload, save a private File on the conversation, and add an AI Attachment."""
	checked = upload.check(file_name, data, voice=voice)
	if not voice:
		pending = frappe.db.count(
			"AI Attachment", {"conversation": conv.name, "sent": 0, "kind": ["!=", "voice"]}
		)
		if pending >= (settings.get().max_files_per_message or 5):
			frappe.throw(_("Too many files for one message."), upload.UploadRefusedError)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": checked.file_name,
			"content": checked.data,
			"is_private": 1,
			"attached_to_doctype": "AI Conversation",
			"attached_to_name": conv.name,
		}
	).insert(ignore_permissions=True)
	return frappe.get_doc(
		{
			"doctype": "AI Attachment",
			"conversation": conv.name,
			"user": frappe.session.user,
			"file": file.name,
			"file_name": checked.file_name,
			"mime_type": checked.mime_type,
			"size_bytes": len(checked.data),
			"kind": checked.kind,
			"status": "Uploaded",
		}
	).insert(ignore_permissions=True)


def enqueue_processing(attachment: str):
	frappe.enqueue(
		"ai_assistant.services.attachments.process",
		queue="short",
		enqueue_after_commit=True,
		now=bool(frappe.in_test),
		attachment=attachment,
	)


def process(attachment: str):
	"""Background job: extract, choose delivery, index large text, publish the status."""
	att = load_own(attachment)
	att.db_set("status", "Processing")
	try:
		result = processor.process(att.kind, read_bytes(att), att.file_name, att.mime_type, att.conversation)
		delivery, text = result.delivery, result.text
		if delivery == "indexed":
			cut = _index_or_cut(att, text)
			delivery, text = ("text", cut) if cut else ("indexed", processor.display_text(text))
		att.db_set(
			{
				"status": "Ready",
				"delivery": delivery,
				"extracted_text": text,
				"page_count": result.page_count or 0,
				"duration_seconds": result.duration_seconds or 0,
				"transcript": result.transcript,
				"error": None,
			}
		)
	except Exception as e:
		frappe.clear_messages()
		if not isinstance(e, frappe.ValidationError):
			frappe.log_error(f"AI Assistant attachment {attachment} failed")
		att.db_set({"status": "Failed", "error": str(e)[:500] or _("The file could not be read.")})
	_publish(att)
	if not frappe.in_test:
		frappe.db.commit()


def for_message(conv, names: list[str] | None) -> list[str]:
	"""Attachments the user may send with a message: theirs, this conversation's, Ready, not sent yet."""
	names = list(dict.fromkeys(names or []))
	if len(names) > (settings.get().max_files_per_message or 5):
		frappe.throw(_("Too many files for one message."))
	for name in names:
		att = load_own(name)
		if att.conversation != conv.name or att.kind == "voice":
			frappe.throw(_("This file belongs to another conversation."), frappe.PermissionError)
		if att.status != "Ready":
			frappe.throw(_("Wait until {0} is ready.").format(att.file_name))
		if att.sent:
			frappe.throw(_("{0} was already sent.").format(att.file_name))
	return names


def mark_sent(names: list[str]):
	for name in names:
		frappe.db.set_value("AI Attachment", name, "sent", 1)


def exists(name: str) -> bool:
	return bool(name) and bool(frappe.db.exists("AI Attachment", name))


def load_own(name: str):
	if not name or not frappe.db.exists("AI Attachment", name):
		frappe.throw(_("File not found."), frappe.DoesNotExistError)
	att = frappe.get_doc("AI Attachment", name)
	att.check_permission("read")
	if att.user != frappe.session.user:
		frappe.throw(_("This file belongs to another user."), frappe.PermissionError)
	return att


def read_bytes(att) -> bytes:
	file = frappe.get_doc("File", att.file)
	file.check_permission("read")
	content = file.get_content()
	return content.encode() if isinstance(content, str) else content


def remove(name: str):
	att = load_own(name)
	if att.sent:
		frappe.throw(_("A file that was sent cannot be removed."))
	_delete(att)


def purge_old():
	"""Daily: delete conversations older than the retention period with everything that belongs to them."""
	days = settings.get().conversation_retention_days
	if not days:
		return
	cutoff = add_days(now_datetime(), -days)
	for name in frappe.get_all(
		"AI Conversation",
		filters={"modified": ["<", cutoff], "status": ["not in", ("Running",)]},
		pluck="name",
	):
		purge_conversation(name)


def purge_conversation(name: str):
	from ai_assistant.persistence.checkpointer import FrappeCheckpointSaver

	frappe.flags.ai_assistant_purge = True
	try:
		for att in frappe.get_all("AI Attachment", filters={"conversation": name}, pluck="name"):
			_delete(frappe.get_doc("AI Attachment", att))
		for doctype in ("AI Message", "AI Action Request"):
			for row in frappe.get_all(doctype, filters={"conversation": name}, pluck="name"):
				frappe.delete_doc(doctype, row, ignore_permissions=True, force=True)
		if schema.table_exists(EMBEDDING_TABLE):
			frappe.db.sql(f"delete from `{EMBEDDING_TABLE}` where conversation = %s", name)
		FrappeCheckpointSaver().delete_thread(name)
		for file in frappe.get_all(
			"File", filters={"attached_to_doctype": "AI Conversation", "attached_to_name": name}, pluck="name"
		):
			frappe.delete_doc("File", file, ignore_permissions=True, force=True)
		frappe.delete_doc("AI Conversation", name, ignore_permissions=True, force=True)
	finally:
		frappe.flags.ai_assistant_purge = False


def _index_or_cut(att, text: str) -> str | None:
	"""Index large text in the conversation's chunks; without an embedding model, cut it instead."""
	from langchain_text_splitters import RecursiveCharacterTextSplitter

	from ai_assistant.llm import registry
	from ai_assistant.rag.store import FrappeVectorStore

	limit = settings.get().max_attachment_text_chars or 30000
	try:
		embeddings = registry.get_embeddings()
	except registry.ModelNotConfiguredError:
		frappe.clear_messages()
		return text[:limit] + "\n\n" + _("[The file was cut here because it is too long.]")
	chunks = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150).split_text(text)
	meta = {"source_doctype": SOURCE, "source_name": att.name, "title": att.file_name}
	FrappeVectorStore(embeddings, conversation=att.conversation).add_texts(
		chunks, [{**meta, "chunk_no": i} for i in range(len(chunks))]
	)
	return None


def _delete(att):
	if schema.table_exists(EMBEDDING_TABLE):
		frappe.db.sql(
			f"delete from `{EMBEDDING_TABLE}` where source_doctype = %s and source_name = %s",
			(SOURCE, att.name),
		)
	file = att.file
	frappe.delete_doc("AI Attachment", att.name, ignore_permissions=True, force=True)
	if file and frappe.db.exists("File", file):
		frappe.delete_doc("File", file, ignore_permissions=True, force=True)


def _publish(att):
	frappe.publish_realtime(
		"ai_assistant_stream",
		{
			"conversation": att.conversation,
			"type": "attachment_status",
			"attachment": att.name,
			"status": att.status,
			"delivery": att.delivery,
			"error": att.error,
		},
		user=att.user,
		after_commit=True,
	)
