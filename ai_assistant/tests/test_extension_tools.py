from unittest.mock import patch

from frappe.tests import IntegrationTestCase
from langchain.tools import tool

from ai_assistant import tools


@tool
def sample_extension(text: str) -> dict:
	"""Echo the text."""
	return {"text": text}


@tool
def list_documents(doctype: str) -> dict:
	"""A tool that reuses a core tool name."""
	return {}


NOT_A_TOOL = "plain string"


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


def _hooks(*paths):
	return patch(
		"frappe.get_hooks",
		side_effect=lambda name, *a, **k: list(paths) if name == "ai_assistant_read_tools" else [],
	)
