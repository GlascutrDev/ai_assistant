import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.services import access, settings
from ai_assistant.tests import factories


class TestAssistantSettings(IntegrationTestCase):
	def test_password_in_child_row_survives_save(self):
		factories.configure()
		doc = frappe.get_single(settings.SETTINGS)
		doc.assistant_name = "Changed"
		doc.save()
		doc = frappe.get_single(settings.SETTINGS)
		self.assertEqual(doc.providers[0].get_password("api_key"), "sk-test-not-a-real-key")

	def test_main_model_must_be_chat_with_tools(self):
		with self.assertRaises(frappe.ValidationError):
			factories.configure(main_model="fake-embed")

	def test_main_model_required_when_enabled(self):
		with self.assertRaises(frappe.ValidationError):
			factories.configure(main_model="")

	def test_enabled_model_needs_enabled_provider(self):
		doc = factories.configure()
		doc.providers[0].enabled = 0
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_embedding_change_marks_index_stale(self):
		doc = factories.configure()
		doc.models[3].dimensions = 16
		doc.save()
		self.assertTrue(doc.index_stale)

	def test_ai_doctypes_always_blocked(self):
		factories.configure(blocked_doctypes="")
		self.assertTrue(settings.is_blocked("AI Conversation"))
		self.assertTrue(settings.is_blocked("User"))
		self.assertFalse(settings.is_blocked("ToDo"))


class TestAccess(IntegrationTestCase):
	def test_role_grants_access(self):
		factories.configure()
		self.assertTrue(access.has_access(factories.assistant_user()))
		self.assertFalse(access.has_access(factories.assistant_user(roles=(factories.role(),))))

	def test_allowed_roles_grant_access(self):
		factories.configure(allowed_roles=[{"role": factories.role()}])
		self.assertTrue(access.has_access(factories.assistant_user(roles=(factories.role(),))))

	def test_disabled_rejects(self):
		factories.configure(enabled=0)
		user = factories.assistant_user()
		with self.set_user(user), self.assertRaises(access.AssistantDisabledError):
			access.require_user()

	def test_conversation_owner_only(self):
		factories.configure()
		owner, other = factories.assistant_user(), factories.assistant_user()
		conv = frappe.get_doc({"doctype": "AI Conversation", "user": owner, "title": "x"}).insert(
			ignore_permissions=True
		)
		with self.set_user(owner):
			self.assertTrue(frappe.has_permission("AI Conversation", "read", conv.name))
		with self.set_user(other):
			self.assertFalse(frappe.has_permission("AI Conversation", "read", conv.name))
			self.assertEqual(frappe.get_list("AI Conversation", filters={"name": conv.name}), [])
