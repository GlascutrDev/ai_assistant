import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.llm import connection, providers, registry
from ai_assistant.tests import factories, fake_llm


class TestRegistry(IntegrationTestCase):
	def setUp(self):
		registry.clear_cache()

	def test_builds_main_model_from_settings(self):
		factories.configure()
		model = registry.get_main_model()
		self.assertEqual(type(model).__name__, "ChatOpenAI")
		self.assertEqual(model.model_name, "fake-main")
		self.assertEqual(model.max_tokens, 1024)

	def test_settings_change_rebuilds_model(self):
		factories.configure()
		first = registry.get_main_model()
		factories.configure(main_model="fake-candidate")
		self.assertEqual(registry.get_main_model().model_name, "fake-candidate")
		self.assertIsNot(first, registry.get_main_model())

	def test_disabled_provider_refused(self):
		doc = factories.configure()
		doc.models[0].enabled = 0
		doc.main_model = "fake-candidate"
		doc.save()
		with self.assertRaises(registry.ModelNotConfiguredError):
			registry.get_chat_model("fake-main")

	def test_moonshot_uses_default_base_url(self):
		kwargs = providers.chat_kwargs(
			"Moonshot", api_key="k", base_url=None, max_tokens=10, temperature=0.2, timeout=5
		)
		self.assertEqual(kwargs["base_url"], "https://api.moonshot.ai/v1")

	def test_redact_removes_key(self):
		doc = factories.configure()
		message = registry.redact("bad key sk-test-not-a-real-key", doc.providers[0])
		self.assertNotIn("sk-test-not-a-real-key", message)


class TestConnection(IntegrationTestCase):
	def test_connection_logs_usage(self):
		factories.configure()
		with fake_llm.use_models(chat={"fake-main": fake_llm.fake_chat("ok")}):
			result = connection.test(factories.FAKE_PROVIDER)
		self.assertTrue(result["ok"])
		self.assertTrue(frappe.db.exists("AI Usage Log", {"purpose": "test", "profile_id": "fake-main"}))

	def test_connection_error_is_redacted(self):
		factories.configure()
		failing = fake_llm.fake_chat(lambda m: (_ for _ in ()).throw(RuntimeError("sk-test-not-a-real-key")))
		with fake_llm.use_models(chat={"fake-main": failing}):
			result = connection.test(factories.FAKE_PROVIDER)
		self.assertFalse(result["ok"])
		self.assertNotIn("sk-test-not-a-real-key", result["error"])


class TestDefaultTemperature(IntegrationTestCase):
	def test_temperature_omitted_when_model_default_is_used(self):
		kwargs = providers.chat_kwargs(
			"Anthropic", api_key="k", base_url=None, max_tokens=10, temperature=None, timeout=5
		)
		self.assertNotIn("temperature", kwargs)
		doc = factories.configure()
		doc.models[0].use_default_temperature = 1
		doc.save()
		registry.clear_cache()
		self.assertIsNone(registry.get_main_model().temperature)
