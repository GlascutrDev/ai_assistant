import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.persistence import schema
from ai_assistant.rag import indexer
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tools import knowledge

QUERY = "warehouse packing procedure apples bananas"


def chunk_texts(doctype: str, name: str) -> list[str]:
	return [
		r[0]
		for r in frappe.db.sql(
			f"select content from `{schema.EMBEDDING_TABLE}` where source_doctype=%s and source_name=%s",
			(doctype, name),
		)
	]


class TestRag(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		schema.create_embedding_table(8, drop=True)

	def setUp(self):
		factories.configure(
			rag_enabled=1, knowledge_sources=[{"source_doctype": "Note", "enabled": 1}], index_stale=0
		)
		indexer.clear_source_cache()
		self.models = fake_llm.use_models()
		self.models.__enter__()
		self.addCleanup(self.models.__exit__, None, None, None)

	def search(self, user: str, query: str = QUERY) -> dict:
		with self.set_user(user):
			return knowledge.search_knowledge.invoke({"query": query})

	def test_ac19_unreadable_chunk_never_returned(self):
		user, other = factories.assistant_user(), factories.assistant_user()
		with self.set_user(user):
			mine = factories.note("Mine", content="warehouse packing procedure apples")
		with self.set_user(other):
			secret = factories.note("Secret", content=QUERY)
		result = self.search(user)
		names = [r["name"] for r in result["results"]]
		self.assertIn(mine.name, names)
		self.assertNotIn(secret.name, names)
		self.assertIn(secret.name, [r["name"] for r in self.search(other)["results"]])

	def test_ac20_knowledge_document_by_role(self):
		role = factories.role("AI Test Knowledge Role")
		doc = frappe.get_doc(
			{
				"doctype": "AI Knowledge Document",
				"title": "Packing SOP",
				"content": f"<p>{QUERY}</p>",
				"visible_to_roles": [{"role": role}],
				"enabled": 1,
			}
		).insert()
		allowed = factories.assistant_user(roles=("AI Assistant User", role))
		denied = factories.assistant_user()
		self.assertIn(doc.name, [r["name"] for r in self.search(allowed)["results"]])
		self.assertNotIn(doc.name, [r["name"] for r in self.search(denied)["results"]])

	def test_ac21_update_replaces_and_delete_removes_chunks(self):
		user = factories.assistant_user()
		with self.set_user(user):
			note = factories.note("Changing", content="first version text")
			self.assertTrue(any("first version" in t for t in chunk_texts("Note", note.name)))
			note.content = "second version text"
			note.save()
			texts = chunk_texts("Note", note.name)
			self.assertTrue(any("second version" in t for t in texts))
			self.assertFalse(any("first version" in t for t in texts))
			note.delete()
		self.assertEqual(chunk_texts("Note", note.name), [])

	def test_stale_index_refuses_search(self):
		factories.configure(rag_enabled=1, index_stale=1)
		result = self.search(factories.assistant_user())
		self.assertIn("error", result)

	def test_usage_logged_for_embeddings(self):
		with self.set_user(factories.assistant_user()):
			factories.note("Usage", content="some text to embed")
		self.assertTrue(
			frappe.db.exists("AI Usage Log", {"purpose": "embedding", "profile_id": "fake-embed"})
		)
