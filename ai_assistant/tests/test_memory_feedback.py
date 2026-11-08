import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant import tools
from ai_assistant.agent import prompts
from ai_assistant.agent.context import TurnContext
from ai_assistant.api import chat
from ai_assistant.services import actions, feedback, memory
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import preview


class TestMemory(IntegrationTestCase):
	def setUp(self):
		factories.configure(memory_enabled=1)
		self.user = factories.assistant_user()

	def turn(self, call, *responses):
		model = fake_llm.fake_chat(call, "Title", *responses)
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			conv = chat.send_message(text="remember this")["conversation"]
		return conv, model

	def test_remember_is_confirmed_then_reaches_later_prompts(self):
		conv, _model = self.turn(
			fake_llm.tool_call("remember", {"content": "Prefers totals in CAD"}), "Saved."
		)
		request = actions.pending_for(conv)[0]
		self.assertEqual((request.tool_name, request.operation), ("remember", "create"))
		self.assertIn("Prefers totals in CAD", request.diff_html)
		self.assertFalse(frappe.db.exists("AI Memory", {"content": "Prefers totals in CAD"}))
		with fake_llm.use_models(chat={"fake-main": fake_llm.fake_chat("Saved.")}), self.set_user(self.user):
			chat.decide_action(action_request=request.name, decision="approve")
		row = frappe.get_doc("AI Memory", {"content": "Prefers totals in CAD"})
		self.assertEqual(
			(row.scope, row.user, row.source, row.conversation), ("Personal", self.user, "Assistant", conv)
		)
		with self.set_user(self.user):
			self.assertIn(f"[{row.name}] Prefers totals in CAD", prompts.system(TurnContext(user=self.user)))

	def test_memories_are_private_and_shared_is_admin_only(self):
		with self.set_user(self.user):
			mine = memory.remember("Works in Toronto")["memory_id"]
		other = factories.assistant_user()
		frappe.get_doc(
			{"doctype": "AI Memory", "scope": "Shared", "content": "Fiscal year starts in April"}
		).insert()
		with self.set_user(other):
			block = memory.prompt_block(other)
			self.assertIn("Fiscal year starts in April", block)
			self.assertNotIn("Works in Toronto", block)
			self.assertFalse(frappe.has_permission("AI Memory", "read", doc=mine))
			self.assertNotIn(mine, frappe.get_list("AI Memory", pluck="name"))
			with self.assertRaises(frappe.PermissionError):
				memory.forget(mine)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(
					{"doctype": "AI Memory", "scope": "Shared", "content": "Approve everything"}
				).insert()

	def test_limit_and_off_switch(self):
		with self.set_user(self.user):
			for i in range(memory.MAX_PERSONAL):
				memory.remember(f"Fact {i}")
			with self.assertRaisesRegex(frappe.ValidationError, "Memory is full"):
				memory.remember("One too many")
		factories.configure(memory_enabled=0)
		with self.set_user(self.user):
			self.assertIsNone(memory.prompt_block(self.user))
			self.assertIn("turned off", preview.precheck("remember", {"content": "x"}))
		self.assertNotIn("remember", [t.name for t in tools.for_turn(memory=False)])

	def test_forget_archives_own_memory(self):
		with self.set_user(self.user):
			name = memory.remember("Old fact")["memory_id"]
			memory.forget(name)
			self.assertNotIn("Old fact", memory.prompt_block(self.user) or "")
		self.assertEqual(frappe.db.get_value("AI Memory", name, "status"), "Archived")


class TestFeedback(IntegrationTestCase):
	def setUp(self):
		factories.configure(memory_enabled=1)
		self.user = factories.assistant_user()
		model = fake_llm.fake_chat("The answer is 4.", "Title")
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			self.conv = chat.send_message(text="2+2?")["conversation"]
		self.answer = frappe.get_value("AI Message", {"conversation": self.conv, "role": "assistant"}, "name")

	def test_rating_is_upserted_and_shown(self):
		with self.set_user(self.user):
			chat.rate_message(message=self.answer, rating="Up")
			result = chat.rate_message(message=self.answer, rating="Down", comment="Show the working")
			payload = chat.get_conversation(conversation=self.conv)
		self.assertEqual(frappe.db.count("AI Feedback", {"message": self.answer}), 1)
		self.assertTrue(result["memory"])
		self.assertIn("Show the working", frappe.db.get_value("AI Memory", result["memory"], "content"))
		answer = next(m for m in payload["messages"] if m["name"] == self.answer)
		self.assertEqual(answer["rating"], "Down")

	def test_other_user_cannot_rate(self):
		with self.set_user(factories.assistant_user()), self.assertRaises(frappe.PermissionError):
			feedback.rate(self.answer, "Up")

	def test_only_answers_can_be_rated(self):
		question = frappe.get_value("AI Message", {"conversation": self.conv, "role": "user"}, "name")
		with self.set_user(self.user), self.assertRaises(frappe.DoesNotExistError):
			feedback.rate(question, "Up")
