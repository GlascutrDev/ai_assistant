import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.tests import IntegrationTestCase

from ai_assistant.tests import factories
from ai_assistant.tools import meta, read, reports


def last_audit(tool_name: str) -> dict:
	return frappe.get_all(
		"AI Audit Log",
		filters={"tool_name": tool_name},
		fields=["outcome", "target_doctype", "user", "error"],
		order_by="creation desc",
		limit=1,
	)[0]


class TestReadTools(IntegrationTestCase):
	def setUp(self):
		factories.configure()

	def test_ac03_user_permission_limits_list(self):
		allowed, other = factories.role("AI Test Allowed"), factories.role("AI Test Other")
		user = factories.assistant_user(
			roles=("AI Assistant User", "System Manager"), user_permissions={"Role": allowed}
		)
		factories.todo("for allowed", role=allowed)
		factories.todo("for other", role=other)
		with self.set_user(user):
			result = read.list_documents.invoke({"doctype": "ToDo", "fields": ["name", "role"], "limit": 100})
		self.assertIn(allowed, [r.get("role") for r in result["rows"]])
		self.assertNotIn(other, [r.get("role") for r in result["rows"]])

	def test_ac04_get_document_denied(self):
		owner, user = factories.assistant_user(), factories.assistant_user()
		with self.set_user(owner):
			todo = factories.todo("secret text")
		with self.set_user(user):
			result = read.get_document.invoke({"doctype": "ToDo", "name": todo.name})
		self.assertEqual(result["outcome"], "permission_denied")
		self.assertNotIn("secret text", frappe.as_json(result))
		audit = last_audit("get_document")
		self.assertEqual((audit.outcome, audit.user), ("permission_denied", user))

	def test_ac05_permlevel_field_hidden(self):
		user = factories.assistant_user()
		with self.set_user(user):
			todo = factories.todo("hidden at permlevel 1")
		setter = make_property_setter(
			"ToDo", "description", "permlevel", 1, "Int", validate_fields_for_doctype=False
		)
		frappe.clear_cache(doctype="ToDo")
		self.addCleanup(frappe.clear_cache, doctype="ToDo")
		self.addCleanup(frappe.delete_doc, "Property Setter", setter.name, force=True)
		with self.set_user(user):
			result = read.get_document.invoke({"doctype": "ToDo", "name": todo.name})
			described = meta.describe_doctype.invoke({"doctype": "ToDo"})
		self.assertEqual(result["document"]["name"], todo.name)
		self.assertNotIn("description", result["document"])
		self.assertNotIn("description", [f["fieldname"] for f in described["fields"]])

	def test_ac06_blocked_doctype(self):
		user = factories.assistant_user(roles=("AI Assistant User", "System Manager"))
		with self.set_user(user):
			for doctype in ("User", "AI Conversation", "Server Script"):
				result = read.list_documents.invoke({"doctype": doctype})
				self.assertEqual(result["outcome"], "blocked_doctype", doctype)
			found = meta.find_doctypes.invoke({"query": "user role"})
		names = {d["doctype"] for d in found["doctypes"]}
		self.assertFalse(names & {"User", "Role", "Has Role", "User Permission"})
		self.assertEqual(last_audit("find_doctypes").outcome, "ok")

	def test_unreadable_filter_field_refused(self):
		user = factories.assistant_user()
		with self.set_user(user):
			result = read.list_documents.invoke({"doctype": "ToDo", "filters": {"no_such_field": 1}})
		self.assertIn("error", result)
		self.assertEqual(last_audit("list_documents").outcome, "validation_error")

	def test_count_and_aggregate(self):
		user = factories.assistant_user()
		with self.set_user(user):
			factories.todo("a", priority="High")
			factories.todo("b", priority="High")
			count = read.count_documents.invoke({"doctype": "ToDo", "filters": {"priority": "High"}})
			grouped = read.aggregate.invoke(
				{"doctype": "ToDo", "metrics": [{"function": "count"}], "group_by": "priority"}
			)
		self.assertEqual(count["count"], 2)
		self.assertEqual(grouped["rows"][0]["count"], 2)

	def test_list_is_clipped(self):
		factories.configure(max_tool_result_chars=600)
		user = factories.assistant_user()
		with self.set_user(user):
			for i in range(20):
				factories.todo(f"long description {i} " + "x" * 50)
			result = read.list_documents.invoke({"doctype": "ToDo", "fields": ["name", "description"]})
		self.assertTrue(result.get("truncated"))
		self.assertLessEqual(len(frappe.as_json(result, indent=None)), 600)

	def test_report_on_blocked_doctype_refused(self):
		user = factories.assistant_user(roles=("AI Assistant User", "System Manager"))
		report = frappe.get_all(
			"Report", filters={"ref_doctype": "User", "report_type": "Script Report"}, limit=1
		)
		if not report:
			self.skipTest("No Script Report on User")
		with self.set_user(user):
			result = reports.run_report.invoke({"report_name": report[0].name})
		self.assertEqual(result["outcome"], "blocked_doctype")
