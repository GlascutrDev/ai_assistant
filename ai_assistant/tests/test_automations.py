from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from ai_assistant.services import automation_run, automations
from ai_assistant.tests import factories, fake_llm


class TestAutomations(IntegrationTestCase):
	def setUp(self):
		factories.configure(automations_enabled=1)
		automations.clear_cache()
		self.user = factories.assistant_user()

	def make(self, **values):
		with self.set_user(self.user):
			doc = frappe.get_doc(
				{
					"doctype": "AI Automation",
					"title": "Daily leads",
					"event": "Schedule",
					"cron": "0 9 * * 1-5",
					"prompt": "Summarize my open ToDos.",
					**values,
				}
			).insert()
		automations.clear_cache()
		return doc

	def execute(self, doc, *responses, **kwargs):
		model = fake_llm.fake_chat(*responses)
		with fake_llm.use_models(chat={"fake-main": model}):
			automation_run.run(doc.name, **kwargs)
		frappe.set_user("Administrator")
		return frappe.get_doc("AI Automation", doc.name)

	def test_validation(self):
		with self.assertRaisesRegex(frappe.ValidationError, "every 15 minutes"):
			self.make(cron="*/5 * * * *")
		with self.assertRaisesRegex(frappe.ValidationError, "valid cron"):
			self.make(cron="every morning")
		with self.assertRaisesRegex(frappe.ValidationError, "cannot watch"):
			self.make(event="Document Event", document_type="User", doc_event="On Update")
		with self.assertRaisesRegex(frappe.ValidationError, "not submittable"):
			self.make(event="Document Event", document_type="ToDo", doc_event="On Submit")
		doc = self.make()
		self.assertEqual(doc.user, self.user)

	def test_owner_only(self):
		doc = self.make()
		with self.set_user(factories.assistant_user()):
			self.assertFalse(frappe.has_permission("AI Automation", "read", doc=doc.name))
			self.assertEqual(frappe.get_list("AI Automation", pluck="name"), [])

	def test_schedule_is_due_once_per_cron_time(self):
		doc = self.make(cron="0 9 * * *")
		monday_9 = now_datetime().replace(hour=9, minute=0, second=30, microsecond=0)
		doc.last_run_at = add_to_date(monday_9, days=-1)
		self.assertTrue(automations.is_due(doc, monday_9))
		doc.last_run_at = monday_9
		self.assertFalse(automations.is_due(doc, add_to_date(monday_9, minutes=30)))

	def test_scheduled_run_answers_as_owner_and_emails(self):
		doc = self.make(email_result=1)
		with patch("frappe.sendmail") as mailed:
			doc = self.execute(doc, "You have 2 open ToDos.", "Title")
		self.assertEqual(doc.last_status, "Answered")
		conv = frappe.get_doc("AI Conversation", doc.last_conversation)
		self.assertEqual((conv.user, conv.automation), (self.user, doc.name))
		self.assertEqual(mailed.call_args.kwargs["recipients"], [self.user])
		self.assertIn("2 open ToDos", mailed.call_args.kwargs["message"])
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": self.user, "document_name": conv.name})
		)

	def test_writes_wait_for_the_owner(self):
		doc = self.make()
		call = fake_llm.tool_call(
			"create_document", {"doctype": "ToDo", "values": {"description": "AUTO TODO"}}
		)
		doc = self.execute(doc, call, "Title")
		self.assertEqual(doc.last_status, "Waiting for approval")
		self.assertFalse(frappe.db.exists("ToDo", {"description": "AUTO TODO"}))
		request = frappe.get_value(
			"AI Action Request", {"conversation": doc.last_conversation}, ["status", "user"], as_dict=True
		)
		self.assertEqual((request.status, request.user), ("Pending", self.user))

	def test_document_event_matches_filters_and_owner_permission(self):
		self.make(
			title="High ToDos",
			event="Document Event",
			document_type="ToDo",
			doc_event="After Insert",
			filters_json='{"priority": "High"}',
		)
		model = fake_llm.fake_chat("Noted.", "Title", "Noted.", "Title")
		with fake_llm.use_models(chat={"fake-main": model}):
			with self.set_user(self.user):
				high = factories.todo("urgent", priority="High").name
				factories.todo("later", priority="Low")
			with self.set_user(factories.assistant_user()):
				factories.todo("someone else's", priority="High")
		frappe.set_user("Administrator")
		runs = frappe.get_all(
			"AI Conversation", filters={"user": self.user, "automation": ["is", "set"]}, pluck="context_name"
		)
		self.assertEqual(runs, [high])

	def test_off_switch_and_loop_guard(self):
		doc = self.make(event="Document Event", document_type="ToDo", doc_event="After Insert")
		frappe.flags.ai_automation = "running"
		try:
			with self.set_user(self.user):
				factories.todo("inside a run")
		finally:
			frappe.flags.ai_automation = None
		factories.configure(automations_enabled=0)
		with self.set_user(self.user):
			factories.todo("while off")
		self.assertFalse(frappe.db.exists("AI Conversation", {"automation": doc.name}))
		self.assertEqual(automations.due_schedules(), [])
