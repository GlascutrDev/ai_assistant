import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import chat
from ai_assistant.services import access, conversations
from ai_assistant.tests import factories, fake_llm


def usage_rows(conversation: str) -> list:
	return frappe.get_all(
		"AI Usage Log",
		filters={"conversation": conversation},
		fields=["profile_id", "purpose"],
		order_by="creation",
	)


def roles_of(conversation: str) -> list[str]:
	return frappe.get_all(
		"AI Message", filters={"conversation": conversation}, pluck="role", order_by="idx_in_thread asc"
	)


class TestChat(IntegrationTestCase):
	def setUp(self):
		factories.configure()
		self.user = factories.assistant_user()

	def chat(self, text: str, *responses, conversation=None, models=None, **kwargs):
		models = models or {"fake-main": fake_llm.fake_chat(*responses)}
		with fake_llm.use_models(chat=models), self.set_user(self.user):
			return chat.send_message(text=text, conversation=conversation, **kwargs)

	def test_ac01_no_access(self):
		outsider = factories.assistant_user(roles=(factories.role(),))
		with self.set_user(outsider), self.assertRaises(frappe.PermissionError):
			chat.send_message(text="hi")

	def test_ac02_disabled(self):
		factories.configure(enabled=0)
		with self.set_user(self.user):
			for call in (
				lambda: chat.send_message(text="hi"),
				lambda: chat.list_conversations(),
				lambda: chat.cancel_turn(conversation="x"),
			):
				with self.assertRaises(access.AssistantDisabledError):
					call()
			self.assertFalse(chat.get_bootstrap()["enabled"])

	def test_turn_with_tool_call(self):
		with self.set_user(self.user):
			factories.todo("first")
		result = self.chat(
			"How many ToDos do I have?",
			fake_llm.tool_call("count_documents", {"doctype": "ToDo"}),
			"You have 1 ToDo.",
			"ToDo count",
		)
		conv = frappe.get_doc("AI Conversation", result["conversation"])
		self.assertEqual(conv.status, "Active")
		self.assertEqual(conv.title, "ToDo count")
		self.assertEqual(roles_of(conv.name), ["user", "tool", "assistant"])
		tool_row = frappe.get_all(
			"AI Message",
			filters={"conversation": conv.name, "role": "tool"},
			fields=["content", "tool_status"],
		)[0]
		self.assertIn('"count": 1', tool_row.content)
		self.assertEqual(tool_row.tool_status, "ok")
		purposes = [r.purpose for r in usage_rows(conv.name)]
		self.assertEqual(purposes.count("agent"), 2)
		self.assertIn("title", purposes)
		self.assertTrue(
			frappe.db.exists("AI Audit Log", {"conversation": conv.name, "tool_name": "count_documents"})
		)

	def test_conversation_continues(self):
		first = self.chat("hello", "Hi!", "Greeting")
		model = fake_llm.fake_chat("Again hi!")
		self.chat("hello again", conversation=first["conversation"], models={"fake-main": model})
		self.assertEqual(roles_of(first["conversation"]), ["user", "assistant", "user", "assistant"])
		self.assertEqual(len([m for m in model.calls[0] if m.type == "human"]), 2)

	def test_ac15_main_model_switch(self):
		first = self.chat("hello", "Hi!", "Greeting")
		factories.configure(main_model="fake-candidate")
		self.chat(
			"again",
			conversation=first["conversation"],
			models={"fake-candidate": fake_llm.fake_chat("Hi from candidate")},
		)
		self.assertEqual(usage_rows(first["conversation"])[-1].profile_id, "fake-candidate")

	def test_ac16_user_turn_never_calls_evaluation_model(self):
		models = {
			"fake-main": fake_llm.fake_chat("Hi!", "Title"),
			"fake-eval": fake_llm.fake_chat(raise_error=True),
		}
		result = self.chat("hello", models=models)
		self.assertEqual(roles_of(result["conversation"]), ["user", "assistant"])

	def test_ac25_second_message_while_running(self):
		with self.set_user(self.user):
			conv = conversations.get_or_create(None)
			conversations.set_status(conv.name, "Running")
			with self.assertRaises(conversations.TurnInProgressError):
				chat.send_message(text="hi", conversation=conv.name)

	def test_other_users_conversation_refused(self):
		result = self.chat("hello", "Hi!", "Greeting")
		other = factories.assistant_user()
		with self.set_user(other):
			with self.assertRaises(frappe.PermissionError):
				chat.get_conversation(conversation=result["conversation"])
			with self.assertRaises(frappe.PermissionError):
				chat.send_message(text="hi", conversation=result["conversation"])

	def test_provider_error_ends_turn_with_note(self):
		models = {"fake-main": fake_llm.fake_chat(raise_error=True)}
		result = self.chat("hello", models=models)
		self.assertEqual(roles_of(result["conversation"]), ["user", "system_note"])
		self.assertEqual(frappe.db.get_value("AI Conversation", result["conversation"], "status"), "Active")

	def test_ac24_no_key_in_transcript(self):
		result = self.chat("hello", "Hi!", "Greeting")
		with self.set_user(self.user):
			payload = chat.get_conversation(conversation=result["conversation"])
		self.assertNotIn("sk-test-not-a-real-key", frappe.as_json(payload))


class TestBootstrapReason(IntegrationTestCase):
	def test_admin_sees_setup_hint(self):
		doc = factories.configure(enabled=0)
		doc.models[0].enabled = 0
		doc.main_model = "fake-main"
		doc.save()
		with self.set_user(factories.assistant_user(roles=("System Manager",))):
			boot = chat.get_bootstrap()
		self.assertFalse(boot["enabled"])
		self.assertIn("fake-main", boot["reason"])


class TestJsonArguments(IntegrationTestCase):
	def test_context_sent_as_json_string(self):
		factories.configure()
		user = factories.assistant_user()
		with fake_llm.use_models(chat={"fake-main": fake_llm.fake_chat("Hi!", "Title")}), self.set_user(user):
			result = chat.send_message(
				text="hi", context='{"doctype": "ToDo", "name": null}', attachments="[]"
			)
		self.assertEqual(
			frappe.db.get_value("AI Conversation", result["conversation"], "context_doctype"), "ToDo"
		)

	def test_wrong_json_type_refused(self):
		factories.configure()
		with self.set_user(factories.assistant_user()), self.assertRaises(frappe.ValidationError):
			chat.send_message(text="hi", context="[1, 2]")
