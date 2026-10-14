import frappe

from ai_assistant.llm import connection


@frappe.whitelist(methods=["POST"])
def test_provider(label: str) -> dict:
	frappe.only_for("System Manager")
	return connection.test(label)


@frappe.whitelist(methods=["POST"])
def rebuild_index() -> dict:
	frappe.only_for("System Manager")
	frappe.enqueue(
		"ai_assistant.rag.indexer.rebuild_all",
		queue="long",
		timeout=7200,
		job_id="ai-rebuild-index",
		deduplicate=True,
	)
	return {"queued": True}
