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


@frappe.whitelist(methods=["POST"])
def run_evaluation(target_model: str | None = None) -> str:
	frappe.only_for("System Manager")
	from ai_assistant.evals import runner
	from ai_assistant.services import settings

	runner.assert_allowed()
	doc = runner.create_run_doc(target_model or settings.get().main_model)
	frappe.enqueue(
		"ai_assistant.evals.runner.run",
		queue="long",
		timeout=7200,
		enqueue_after_commit=True,
		now=bool(frappe.in_test),
		evaluation_run=doc.name,
	)
	return doc.name
