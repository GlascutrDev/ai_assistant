"""run_report (SPEC §7.1). frappe.desk.query_report.run checks the report roles and ref DocType."""

import frappe
from frappe import _
from frappe.desk.query_report import run
from langchain.tools import ToolRuntime, tool

from ai_assistant.services import settings
from ai_assistant.tools import base, guard

RUNNABLE_TYPES = ("Query Report", "Script Report")


@tool
def run_report(report_name: str, filters: dict | None = None, runtime: ToolRuntime = None) -> dict:
	"""Run a Query or Script Report the user can open, e.g. "General Ledger" or "Accounts Receivable".
	filters: the report's filter values, e.g. {"company": "...", "from_date": "2026-01-01"}.
	Returns the columns, the first rows, and the total row when the report has one."""
	return base.execute(
		"run_report",
		lambda: _run(report_name, filters or {}),
		operation="report",
		doctype="Report",
		name=report_name,
		args={"report_name": report_name, "filters": filters},
		runtime=runtime,
	)


def _run(report_name: str, filters: dict) -> dict:
	try:
		report = frappe.get_cached_doc("Report", report_name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Report {0} does not exist.").format(report_name), frappe.DoesNotExistError)
	if report.report_type not in RUNNABLE_TYPES:
		frappe.throw(_("Only Query and Script Reports can be run."))
	guard.check(report.ref_doctype, "read")
	result = run(report_name, filters=filters, ignore_prepared_report=True)
	columns = [_column(c) for c in result.get("columns") or []]
	rows = [_row(r, columns) for r in result.get("result") or []]
	limit = settings.max_rows()
	total = rows.pop() if result.get("add_total_row") and rows else None
	return {
		"report": report_name,
		"columns": columns,
		"rows": rows[:limit],
		"total_row": total,
		"row_count": len(rows),
		"more_rows_exist": len(rows) > limit,
	}


def _column(column) -> dict:
	if isinstance(column, str):
		parts = column.split(":")
		return {"fieldname": frappe.scrub(parts[0]), "label": parts[0]}
	return {
		"fieldname": column.get("fieldname") or frappe.scrub(column.get("label", "")),
		"label": column.get("label"),
	}


def _row(row, columns) -> dict:
	if isinstance(row, dict):
		return {
			c["fieldname"]: row.get(c["fieldname"]) for c in columns if row.get(c["fieldname"]) is not None
		}
	return {c["fieldname"]: v for c, v in zip(columns, row, strict=False) if v is not None}
