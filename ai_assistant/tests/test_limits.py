import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from ai_assistant.agent import graph
from ai_assistant.api import chat
from ai_assistant.services import budget
from ai_assistant.tests import factories, fake_llm


def notes_of(conversation: str) -> list[str]:
	return frappe.get_all(
		"AI Message", filters={"conversation": conversation, "role": "system_note"}, pluck="content"
	)


def spend(user: str, tokens: int = 0, cost: float = 0):
	frappe.get_doc(
		{
			"doctype": "AI Usage Log",
			"date": nowdate(),
			"user": user,
			"purpose": "agent",
			"profile_id": "fake-main",
			"input_tokens": tokens,
			"cost": cost,
		}
	).insert(ignore_permissions=True)
	budget.add(user, tokens, cost, "agent")


class TestLimits(IntegrationTestCase):
	def setUp(self):
		factories.configure()
		self.user = factories.assistant_user()

	def send(self, model, text="hi", conversation=None):
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			return chat.send_message(text=text, conversation=conversation)

	def test_ac17_daily_limit_refuses_before_model_call(self):
		factories.configure(user_daily_token_limit=100)
		spend(self.user, tokens=150)
		with self.assertRaises(budget.BudgetExceededError):
			self.send(fake_llm.fake_chat(raise_error=True))

	def test_daily_limit_reached_during_turn(self):
		factories.configure(user_daily_token_limit=15)
		model = fake_llm.fake_chat(fake_llm.tool_call("count_documents", {"doctype": "ToDo"}), "never")
		result = self.send(model)
		self.assertIn("Daily AI limit reached. It resets at midnight.", notes_of(result["conversation"]))
		self.assertEqual(len(model.calls), 1)

	def test_monthly_cost_limit(self):
		factories.configure(site_monthly_cost_limit=1)
		spend(factories.assistant_user(), cost=2)
		with self.assertRaises(budget.BudgetExceededError):
			self.send(fake_llm.fake_chat(raise_error=True))

	def test_ac18_tool_call_limit_ends_turn(self):
		factories.configure(max_tool_calls_per_turn=2)
		calls = [fake_llm.tool_call("count_documents", {"doctype": "ToDo"}, f"call_{i}") for i in range(4)]
		model = fake_llm.fake_chat(*calls, "never reached", "Title")
		result = self.send(model)
		roles = frappe.get_all(
			"AI Message",
			filters={"conversation": result["conversation"]},
			pluck="role",
			order_by="idx_in_thread",
		)
		self.assertEqual(roles.count("tool"), 3)
		self.assertEqual(roles[-1], "assistant")
		self.assertEqual(frappe.db.get_value("AI Conversation", result["conversation"], "status"), "Active")
		self.assertEqual(
			frappe.db.count(
				"AI Audit Log", {"conversation": result["conversation"], "tool_name": "count_documents"}
			),
			2,
		)

	def test_context_window_too_long(self):
		doc = factories.configure()
		doc.models[0].context_window = 5
		doc.save()
		result = self.send(fake_llm.fake_chat(raise_error=True), text="a long question " * 20)
		self.assertIn("This conversation is too long. Start a new one.", notes_of(result["conversation"]))

	def test_summarize_threshold(self):
		factories.configure(summarize_after_tokens=60000)
		self.assertEqual(graph.summarize_at("fake-main"), 60000)
		doc = factories.configure(summarize_after_tokens=90000)
		self.assertEqual(graph.summarize_at("fake-main"), int(doc.models[0].context_window * 0.7))
