from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from langchain.tools import tool

from ai_assistant import tools
from ai_assistant.api import chat
from ai_assistant.services import actions
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import preview


@tool
def sample_extension(text: str) -> dict:
	"""Echo the text."""
	return {"text": text}


@tool
def list_documents(doctype: str) -> dict:
	"""A tool that reuses a core tool name."""
	return {}


@tool
def sample_write(text: str) -> dict:
	"""Store the text."""
	return {"text": text}


@tool
def write_without_spec(text: str) -> dict:
	"""A write tool with no ai_assistant metadata."""
	return {}


def _refuse_bad(args: dict):
	if args.get("text") == "bad":
		frappe.throw("Bad text.")


sample_write.metadata = {
	"ai_assistant": {
		"operation": "create",
		"doctype": "ToDo",
		"precheck": _refuse_bad,
		"preview": lambda args: (["Text"], [(args["text"],)]),
	}
}

NOT_A_TOOL = "plain string"
WRITE_PATH = "ai_assistant.tests.test_extension_tools.sample_write"


class TestExtensionTools(IntegrationTestCase):
	def test_hooked_read_tool_is_offered(self):
		with _hooks("ai_assistant.tests.test_extension_tools.sample_extension"):
			names = [t.name for t in tools.for_turn()]
			read_only = [t.name for t in tools.for_turn(read_only=True)]
		self.assertIn("sample_extension", names)
		self.assertIn("sample_extension", read_only)
		self.assertNotIn("sample_extension", tools.write_tool_names())

	def test_bad_or_clashing_entries_are_skipped(self):
		paths = [
			"ai_assistant.tests.test_extension_tools.NOT_A_TOOL",
			"ai_assistant.tests.test_extension_tools.list_documents",
			"ai_assistant.tests.missing_module.tool",
		]
		with _hooks(*paths), patch("frappe.log_error") as logged:
			found = tools.extension_tools()
		self.assertEqual(found, [])
		self.assertEqual(logged.call_count, 3)

	def test_hooked_write_tool_is_interrupted_and_hidden_in_read_only_mode(self):
		with _hooks(write=[WRITE_PATH]):
			self.assertIn("sample_write", [t.name for t in tools.for_turn()])
			self.assertNotIn("sample_write", [t.name for t in tools.for_turn(read_only=True)])
			self.assertIn("sample_write", tools.write_tool_names())
			self.assertEqual(actions.operation_of("sample_write"), "create")

	def test_write_tool_without_spec_is_skipped(self):
		with (
			_hooks(write=["ai_assistant.tests.test_extension_tools.write_without_spec"]),
			patch("frappe.log_error") as logged,
		):
			self.assertEqual(tools.extension_write_tools(), [])
		logged.assert_called_once()

	def test_card_uses_the_extension_precheck_target_and_escaped_preview(self):
		with _hooks(write=[WRITE_PATH]):
			self.assertEqual(preview.target_of("sample_write", {"text": "x"}), ("ToDo", None))
			self.assertIsNone(preview.precheck("sample_write", {"text": "ok"}))
			self.assertIn("Bad text", preview.precheck("sample_write", {"text": "bad"}))
			html = preview.preview_html("sample_write", {"text": "<b>x</b>"})
		self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
		self.assertNotIn("<b>x</b>", html)


class TestExtensionWriteTurn(IntegrationTestCase):
	def setUp(self):
		factories.configure()
		self.user = factories.assistant_user()

	def test_extension_write_pauses_with_its_preview_and_runs_after_approval(self):
		model = fake_llm.fake_chat(fake_llm.tool_call("sample_write", {"text": "week"}), "Title", "Stored.")
		with _hooks(write=[WRITE_PATH]), fake_llm.use_models(chat={"fake-main": model}):
			with self.set_user(self.user):
				conv = chat.send_message(text="store it")["conversation"]
				request = actions.pending_for(conv)[0]
				self.assertEqual((request.tool_name, request.operation), ("sample_write", "create"))
				self.assertIn("<th>Text</th>", request.diff_html)
				chat.decide_action(action_request=request.name, decision="approve")
		status = frappe.db.get_value("AI Action Request", request.name, "status")
		self.assertEqual(status, "Executed")


def _hooks(*paths, write=()):
	hooks = {"ai_assistant_read_tools": list(paths), "ai_assistant_write_tools": list(write)}
	real = frappe.get_hooks
	return patch(
		"frappe.get_hooks",
		side_effect=lambda name=None, *a, **k: hooks[name] if name in hooks else real(name, *a, **k),
	)
