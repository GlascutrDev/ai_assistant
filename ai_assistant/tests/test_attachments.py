import base64
import io

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import chat
from ai_assistant.attachments.upload import UploadRefusedError
from ai_assistant.persistence import schema
from ai_assistant.persistence.checkpointer import FrappeCheckpointSaver
from ai_assistant.services import actions, conversations
from ai_assistant.services import attachments as files
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import files as file_tools


def docx_bytes(text: str) -> bytes:
	import docx

	document = docx.Document()
	document.add_paragraph(text)
	out = io.BytesIO()
	document.save(out)
	return out.getvalue()


def xlsx_bytes(rows: list[list]) -> bytes:
	from openpyxl import Workbook

	workbook = Workbook()
	for row in rows:
		workbook.active.append(row)
	out = io.BytesIO()
	workbook.save(out)
	return out.getvalue()


def png_bytes() -> bytes:
	from PIL import Image

	out = io.BytesIO()
	Image.new("RGB", (20, 10), "red").save(out, format="PNG")
	return out.getvalue()


def prompt_text(model) -> str:
	return repr([m.content for m in model.calls[0]])


class TestAttachments(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		schema.create_embedding_table(8, drop=True)

	def setUp(self):
		factories.configure(attachments_enabled=1)
		self.user = factories.assistant_user()
		self.models = fake_llm.use_models()
		self.models.__enter__()
		self.addCleanup(self.models.__exit__, None, None, None)

	def upload(self, name: str, data: bytes, user: str | None = None, conversation=None):
		with self.set_user(user or self.user):
			conv = conversations.get_or_create(conversation)
			att = files.create(conv, name, data)
			files.process(att.name)
			return frappe.get_doc("AI Attachment", att.name)

	def send(self, att, *responses, text="What is in the file?"):
		model = fake_llm.fake_chat(*(responses or ("It says hello.", "Title")))
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			chat.send_message(text=text, conversation=att.conversation, attachments=[att.name])
		return model

	def file_count(self) -> int:
		return frappe.db.count("File", {"attached_to_doctype": "AI Conversation"})

	def test_ac33_refused_uploads_create_no_file(self):
		before = self.file_count()
		for name, data in (
			("tool.exe", b"MZ\x90\x00" + b"\x00" * 100),
			("invoice.pdf", b"MZ\x90\x00" + b"\x00" * 100),
			("notes.txt", b"\x89PNG\r\n\x1a\n" + b"\x00" * 50),
		):
			with self.assertRaises(UploadRefusedError, msg=name):
				self.upload(name, data)
		factories.configure(attachments_enabled=1, max_file_size_mb=1)
		with self.assertRaises(UploadRefusedError):
			self.upload("big.txt", b"a" * (2 * 1024 * 1024))
		self.assertEqual(self.file_count(), before)

	def test_ac34_text_kinds_reach_model_as_attachment_block(self):
		cases = {
			"memo.docx": docx_bytes("DOCX marker text"),
			"sheet.xlsx": xlsx_bytes([["Item", "Qty"], ["XLSX marker", 3]]),
			"data.csv": b"item,qty\nCSV marker,4\n",
			"plain.txt": b"TXT marker text",
		}
		for name, data in cases.items():
			att = self.upload(name, data)
			self.assertEqual((att.status, att.delivery), ("Ready", "text"), f"{name}: {att.error}")
			model = self.send(att)
			sent = prompt_text(model)
			self.assertIn(f'<attachment name="{name}"', sent)
			self.assertIn((name.split(".")[0] == "memo" and "DOCX marker") or "marker", sent)

	def test_ac35_image_native_block_or_refused(self):
		att = self.upload("photo.png", png_bytes())
		self.assertEqual(att.delivery, "native")
		model = self.send(att)
		blocks = model.calls[0][-1].content
		self.assertTrue(any(isinstance(b, dict) and b.get("type") == "image" for b in blocks))
		doc = factories.configure(attachments_enabled=1)
		doc.models[0].supports_images = 0
		doc.save()
		with self.assertRaisesRegex(UploadRefusedError, "cannot read images"):
			self.upload("photo2.png", png_bytes())

	def test_ac36_large_text_indexed_and_scoped(self):
		factories.configure(attachments_enabled=1, max_attachment_text_chars=200)
		text = (
			("filler words about nothing. " * 30)
			+ "The secret pallet code is ZEBRA-42. "
			+ ("more filler. " * 30)
		)
		att = self.upload("long.txt", text.encode())
		self.assertEqual(att.delivery, "indexed")
		ctx = fake_llm.FakeRuntime(self.user, att.conversation)
		with self.set_user(self.user):
			found = file_tools.search_attachments.func(query="secret pallet code ZEBRA-42", runtime=ctx)
		self.assertTrue(any("ZEBRA-42" in r["text"] for r in found["results"]))
		other = factories.assistant_user()
		with self.set_user(other):
			conv = conversations.get_or_create(None)
			found = file_tools.search_attachments.func(
				query="secret pallet code ZEBRA-42", runtime=fake_llm.FakeRuntime(other, conv.name)
			)
		self.assertFalse(found["results"])

	def test_ac37_other_users_attachment_refused(self):
		att = self.upload("plain.txt", b"private text")
		other = factories.assistant_user()
		with self.set_user(other):
			conv = conversations.get_or_create(None)
			with self.assertRaises(frappe.PermissionError):
				chat.send_message(text="read it", conversation=conv.name, attachments=[att.name])
			result = file_tools.read_attachment.invoke({"file": att.name})
		self.assertEqual(result["outcome"], "permission_denied")
		self.assertNotIn("private text", frappe.as_json(result))

	def test_ac38_file_on_unreadable_document(self):
		owner = factories.assistant_user()
		with self.set_user(owner):
			todo = factories.todo("owner only")
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "secret.txt",
				"content": b"top secret",
				"is_private": 1,
				"attached_to_doctype": "ToDo",
				"attached_to_name": todo.name,
			}
		).insert(ignore_permissions=True)
		with self.set_user(self.user):
			result = file_tools.read_attachment.invoke({"file": file.name})
		self.assertEqual(result["outcome"], "permission_denied")

	def test_ac39_attach_file_after_confirmation(self):
		with self.set_user(self.user):
			todo = factories.todo("needs a file")
		att = self.upload("plain.txt", b"attach me")
		call = fake_llm.tool_call(
			"attach_file", {"attachment": att.name, "doctype": "ToDo", "name": todo.name}
		)
		model = fake_llm.fake_chat(call, "Title", "Attached.")
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			chat.send_message(
				text="attach it to the ToDo", conversation=att.conversation, attachments=[att.name]
			)
			request = actions.pending_for(att.conversation)[0]
			self.assertFalse(frappe.db.exists("File", {"attached_to_name": todo.name}))
			chat.decide_action(action_request=request.name, decision="approve")
		file = frappe.get_doc("File", {"attached_to_doctype": "ToDo", "attached_to_name": todo.name})
		self.assertTrue(file.is_private)

	def test_ac40_checkpoint_holds_reference_only(self):
		data = png_bytes()
		att = self.upload("photo.png", data)
		self.send(att)
		state = FrappeCheckpointSaver().get_tuple({"configurable": {"thread_id": att.conversation}})
		dump = repr(state.checkpoint["channel_values"])
		stored = base64.b64encode(files.read_bytes(att)).decode()
		self.assertNotIn(stored[:200], dump)
		self.assertIn(att.name, dump)

	def test_ac41_purge_removes_everything(self):
		factories.configure(attachments_enabled=1, max_attachment_text_chars=200)
		att = self.upload("long.txt", ("word " * 400).encode())
		self.send(att)
		conv = att.conversation
		file = att.file
		files.purge_conversation(conv)
		self.assertFalse(frappe.db.exists("AI Conversation", conv))
		self.assertFalse(frappe.db.exists("AI Attachment", att.name))
		self.assertFalse(frappe.db.exists("File", file))
		self.assertFalse(frappe.db.exists("AI Message", {"conversation": conv}))
		chunks = frappe.db.sql(
			f"select count(*) from `{schema.EMBEDDING_TABLE}` where conversation=%s", conv
		)[0][0]
		self.assertEqual(chunks, 0)


class TestUploadLimits(IntegrationTestCase):
	def test_read_upload_stops_at_limit(self):
		factories.configure(attachments_enabled=1, max_file_size_mb=1)
		with self.assertRaises(UploadRefusedError):
			files.read_upload(io.BytesIO(b"a" * (1024 * 1024 + 10)))
		self.assertEqual(len(files.read_upload(io.BytesIO(b"abc"))), 3)
