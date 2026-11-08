from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import chat
from ai_assistant.services import actions
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import bulk, mail, preview


def requests_of(conversation: str) -> list:
	return frappe.get_all(
		"AI Action Request",
		filters={"conversation": conversation},
		fields=["name", "status", "tool_name", "operation", "diff_html", "result"],
		order_by="action_index asc",
	)


class TestBulkWrites(IntegrationTestCase):
	def setUp(self):
		factories.configure()
		self.user = factories.assistant_user()

	def turn(self, call, *responses):
		model = fake_llm.fake_chat(call, "Title", *(responses or ("Done.",)))
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			conv = chat.send_message(text="do it")["conversation"]
			return conv, requests_of(conv)

	def approve(self, request):
		model = fake_llm.fake_chat("Done.")
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			chat.decide_action(action_request=request.name, decision="approve")

	def test_create_many_in_one_confirmed_card(self):
		records = [{"description": "BULK A"}, {"description": "BULK B"}]
		_conv, rows = self.turn(
			fake_llm.tool_call("create_documents", {"doctype": "ToDo", "records": records})
		)
		self.assertEqual(
			[(r.tool_name, r.operation, r.status) for r in rows], [("create_documents", "create", "Pending")]
		)
		self.assertIn("BULK B", rows[0].diff_html)
		self.assertFalse(frappe.db.exists("ToDo", {"description": "BULK A"}))
		self.approve(rows[0])
		self.assertEqual(frappe.db.count("ToDo", {"description": ["like", "BULK %"], "owner": self.user}), 2)

	def test_update_is_all_or_nothing(self):
		with self.set_user(self.user):
			mine = [factories.todo(f"MINE {i}").name for i in range(2)]
		other = factories.assistant_user()
		with self.set_user(other):
			theirs = factories.todo("THEIRS").name
		with self.set_user(self.user):
			error = preview.precheck(
				"update_documents",
				{"doctype": "ToDo", "names": [*mine, theirs], "values": {"priority": "High"}},
			)
			self.assertTrue(error)
			result = bulk.update_documents.invoke(
				{"doctype": "ToDo", "names": [*mine, theirs], "values": {"priority": "High"}}
			)
		self.assertEqual(result["outcome"], "permission_denied")
		self.assertEqual({frappe.db.get_value("ToDo", n, "priority") for n in mine}, {"Medium"})

	def test_update_preview_shows_now_and_new(self):
		with self.set_user(self.user):
			name = factories.todo("PREVIEW").name
			html = preview.preview_html(
				"update_documents", {"doctype": "ToDo", "names": [name], "values": {"priority": "Low"}}
			)
		self.assertIn("Medium", html)
		self.assertIn("Low", html)

	def test_limits_and_blocked_doctypes(self):
		with self.set_user(self.user):
			too_many = preview.precheck(
				"delete_documents", {"doctype": "ToDo", "names": [str(i) for i in range(51)]}
			)
			blocked = preview.precheck("delete_documents", {"doctype": "User", "names": ["Guest"]})
		self.assertIn("50", too_many)
		self.assertIn("cannot access", blocked)


class TestSendEmail(IntegrationTestCase):
	def setUp(self):
		factories.configure()
		self.user = factories.assistant_user()

	def args(self, **extra):
		return {"recipients": ["a@example.com"], "subject": "Hi", "message": "Line 1\n<b>x</b>", **extra}

	def test_sends_after_approval_on_the_record(self):
		with self.set_user(self.user):
			todo = factories.todo("EMAIL ME").name
		call = fake_llm.tool_call("send_email", self.args(reference_doctype="ToDo", reference_name=todo))
		model = fake_llm.fake_chat(call, "Title", "Sent.")
		with (
			patch.object(mail, "make", return_value={"name": "COMM-1"}) as sent,
			fake_llm.use_models(chat={"fake-main": model}),
			self.set_user(self.user),
		):
			conv = chat.send_message(text="email them")["conversation"]
			request = actions.pending_for(conv)[0]
			self.assertEqual((request.operation, request.target_doctype), ("email", "ToDo"))
			sent.assert_not_called()
			chat.decide_action(action_request=request.name, decision="approve")
		kwargs = sent.call_args.kwargs
		self.assertEqual((kwargs["doctype"], kwargs["name"], kwargs["send_email"]), ("ToDo", todo, True))
		self.assertEqual(kwargs["content"], "Line 1<br>&lt;b&gt;x&lt;/b&gt;")

	def test_refused_without_email_permission_or_valid_address(self):
		other = factories.assistant_user()
		with self.set_user(other):
			theirs = factories.todo("NOT YOURS").name
		with self.set_user(self.user):
			mine = factories.todo("MINE").name
			denied = preview.precheck(
				"send_email", self.args(reference_doctype="ToDo", reference_name=theirs)
			)
			no_reference = preview.precheck("send_email", self.args())
			bad = preview.precheck(
				"send_email",
				self.args(recipients=["not an email"], reference_doctype="ToDo", reference_name=mine),
			)
		self.assertIn("email permission", denied)
		self.assertIn("Communication", no_reference)
		self.assertIn("not a valid email", bad)

	def test_read_only_mode_refuses(self):
		factories.configure(read_only_mode=1)
		with self.set_user(self.user):
			self.assertIn(
				"read-only",
				preview.precheck("send_email", self.args(reference_doctype="ToDo", reference_name="x")),
			)
