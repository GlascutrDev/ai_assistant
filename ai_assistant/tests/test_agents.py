from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant import tools
from ai_assistant.api import chat
from ai_assistant.rag.store import FrappeVectorStore
from ai_assistant.services import agents, automation_run, bootstrap
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import knowledge


def agent(title: str, **values) -> str:
	roles = [{"role": r} for r in values.pop("roles", [])]
	sources = [{"source_doctype": s} for s in values.pop("sources", [])]
	return (
		frappe.get_doc(
			{
				"doctype": "AI Agent",
				"title": title,
				"enabled": 1,
				"roles": roles,
				"knowledge_sources": sources,
				**values,
			}
		)
		.insert()
		.name
	)


class TestAgents(IntegrationTestCase):
	def setUp(self):
		factories.configure(automations_enabled=1)
		frappe.db.delete("AI Agent")
		frappe.clear_cache(doctype="AI Agent")
		self.user = factories.assistant_user()

	def turn(self, *responses, agent_name=None, text="hello"):
		model = fake_llm.fake_chat(*(responses or ("Hi.", "Title")))
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			conv = chat.send_message(text=text, agent=agent_name)["conversation"]
		return conv, model

	def test_validation(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Unknown tools: run_python"):
			agent("Bad tools", allowed_tools="list_documents\nrun_python")
		with self.assertRaisesRegex(frappe.ValidationError, "not an enabled knowledge source"):
			agent("Bad source", sources=["ToDo"])
		first, second = agent("First", is_default=1), agent("Second", is_default=1)
		self.assertEqual(frappe.db.get_value("AI Agent", first, "is_default"), 0)
		self.assertEqual(frappe.db.get_value("AI Agent", second, "is_default"), 1)

	def test_agent_narrows_tools_and_adds_instructions(self):
		name = agent(
			"Sales helper",
			description="Answers sales questions.",
			instructions="Always answer in a table.",
			allowed_tools="list_documents\ncount_documents\ncreate_document",
			read_only=1,
		)
		conv, model = self.turn(agent_name=name)
		self.assertEqual(sorted(model.bound_tools), ["count_documents", "list_documents"])
		system = model.calls[0][0].content
		self.assertIn('You are the agent "Sales helper"', system)
		self.assertIn("Always answer in a table.", system)
		self.assertLess(system.index("Untrusted content"), system.index("Always answer in a table."))
		self.assertEqual(frappe.db.get_value("AI Conversation", conv, "agent"), name)
		with self.set_user(self.user):
			self.assertEqual(
				chat.get_conversation(conversation=conv)["conversation"]["agent_title"], "Sales helper"
			)

	def test_role_limits_and_default(self):
		special = factories.role("AI Agent Test Role")
		limited = agent("HR only", roles=[special])
		default = agent("Front desk", is_default=1)
		with self.set_user(self.user):
			self.assertEqual([a["name"] for a in bootstrap.get()["agents"]], [default])
			self.assertFalse(frappe.has_permission("AI Agent", "read", doc=limited))
			self.assertEqual(frappe.get_list("AI Agent", pluck="name"), [default])
			with self.assertRaises(agents.AgentUnavailableError):
				chat.send_message(text="hi", agent=limited)
		conv, _model = self.turn()
		self.assertEqual(frappe.db.get_value("AI Conversation", conv, "agent"), default)

	def test_disabled_agent_stops_its_conversations(self):
		name = agent("Temporary")
		conv, _model = self.turn(agent_name=name)
		frappe.db.set_value("AI Agent", name, "enabled", 0)
		frappe.clear_cache(doctype="AI Agent")
		with self.set_user(self.user), self.assertRaises(agents.AgentUnavailableError):
			chat.send_message(text="again", conversation=conv)

	def test_knowledge_is_scoped_to_the_agent(self):
		factories.configure(automations_enabled=1, rag_enabled=1)
		name = agent("Policies", sources=["AI Knowledge Document"])
		seen = {}

		def search(store, query, k=4, **kwargs):
			seen["sources"] = store.sources
			return []

		runtime = fake_llm.FakeRuntime(self.user, None)
		runtime.context.agent = name
		with (
			patch("ai_assistant.rag.indexer.is_searchable", return_value=True),
			patch.object(FrappeVectorStore, "similarity_search_with_score", search),
			fake_llm.use_models(),
			self.set_user(self.user),
		):
			knowledge.search_knowledge.func(query="returns", runtime=runtime)
		self.assertEqual(seen["sources"], ["AI Knowledge Document"])

	def test_automation_runs_with_its_agent(self):
		name = agent("Reporter", allowed_tools="count_documents")
		with self.set_user(self.user):
			auto = frappe.get_doc(
				{
					"doctype": "AI Automation",
					"title": "Count",
					"event": "Schedule",
					"cron": "0 9 * * *",
					"prompt": "Count my ToDos.",
					"agent": name,
				}
			).insert()
		model = fake_llm.fake_chat("3.", "Title")
		with fake_llm.use_models(chat={"fake-main": model}):
			automation_run.run(auto.name)
		frappe.set_user("Administrator")
		conv = frappe.db.get_value("AI Automation", auto.name, "last_conversation")
		self.assertEqual(frappe.db.get_value("AI Conversation", conv, "agent"), name)
		self.assertEqual(model.bound_tools, ["count_documents"])

	def test_every_tool_name_is_known(self):
		self.assertTrue(
			{"list_documents", "send_email", "remember", "query_spreadsheet"} <= tools.all_tool_names()
		)
