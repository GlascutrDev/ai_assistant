import frappe

from ai_assistant.llm import connection


@frappe.whitelist(methods=["POST"])
def test_provider(label: str) -> dict:
	frappe.only_for("System Manager")
	return connection.test(label)
