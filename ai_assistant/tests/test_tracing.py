from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import chat
from ai_assistant.observability import tracing
from ai_assistant.tests import factories, fake_llm

LANGSMITH_KEY = "lsv2_test_not_a_real_key_000000"


class TestTracing(IntegrationTestCase):
	def setUp(self):
		tracing._clients.clear()

	def test_off_by_default(self):
		factories.configure()
		self.assertIsNone(tracing.get_client())

	def test_ac24_trace_has_run_id_and_no_secrets(self):
		factories.configure(
			langsmith_enabled=1, langsmith_api_key=LANGSMITH_KEY, langsmith_project="test-proj"
		)
		client = MagicMock()
		user = factories.assistant_user()
		with (
			patch.object(tracing, "_build_client", return_value=client) as build,
			fake_llm.use_models(chat={"fake-main": fake_llm.fake_chat("Hi!", "Title")}),
			self.set_user(user),
		):
			result = chat.send_message(text="hello")
		build.assert_called_once()
		self.assertEqual(build.call_args.args[0], LANGSMITH_KEY)
		run_id = frappe.db.get_value(
			"AI Message", {"conversation": result["conversation"], "role": "assistant"}, "langsmith_run_id"
		)
		self.assertTrue(run_id)
		sent = repr(client.mock_calls)
		self.assertIn(result["conversation"], sent)
		self.assertNotIn(LANGSMITH_KEY, sent)
		self.assertNotIn("sk-test-not-a-real-key", sent)

	def test_hide_io_passed_to_client(self):
		factories.configure(langsmith_enabled=1, langsmith_api_key=LANGSMITH_KEY, langsmith_hide_io=1)
		with patch("langsmith.Client") as client_class:
			tracing.get_client()
		self.assertTrue(client_class.call_args.kwargs["hide_inputs"])
		self.assertTrue(client_class.call_args.kwargs["hide_outputs"])

	def test_usage_report(self):
		from ai_assistant.ai_assistant.report.ai_usage_summary import ai_usage_summary

		factories.configure()
		with (
			fake_llm.use_models(chat={"fake-main": fake_llm.fake_chat("Hi!", "Title")}),
			self.set_user(factories.assistant_user()),
		):
			chat.send_message(text="hello")
		columns, rows = ai_usage_summary.execute({"group_by": "Model"})
		self.assertEqual(columns[0]["fieldname"], "profile_id")
		self.assertIn("fake-main", [r.profile_id for r in rows])
