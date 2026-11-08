"""Tool registry. Every tool in write_tool_names() is interrupted for confirmation (CLAUDE.md rule 3)."""

import frappe
from langchain_core.tools import BaseTool

from ai_assistant.tools.bulk import create_documents, delete_documents, update_documents
from ai_assistant.tools.files import attach_file, read_attachment, search_attachments
from ai_assistant.tools.knowledge import search_knowledge
from ai_assistant.tools.mail import send_email
from ai_assistant.tools.memory import forget_memory, remember
from ai_assistant.tools.meta import describe_doctype, find_doctypes
from ai_assistant.tools.read import aggregate, count_documents, get_document, list_documents, search_links
from ai_assistant.tools.reports import run_report
from ai_assistant.tools.spreadsheets import inspect_spreadsheet, query_spreadsheet, write_spreadsheet
from ai_assistant.tools.write import (
	add_comment,
	apply_workflow_action,
	assign_to,
	cancel_document,
	create_document,
	delete_document,
	submit_document,
	update_document,
)

READ_TOOLS = [
	find_doctypes,
	describe_doctype,
	list_documents,
	count_documents,
	aggregate,
	get_document,
	run_report,
	search_links,
	search_knowledge,
	read_attachment,
	search_attachments,
	inspect_spreadsheet,
	query_spreadsheet,
]

WRITE_TOOLS = [
	create_document,
	update_document,
	submit_document,
	cancel_document,
	delete_document,
	add_comment,
	assign_to,
	apply_workflow_action,
	attach_file,
	write_spreadsheet,
	create_documents,
	update_documents,
	delete_documents,
	send_email,
	remember,
	forget_memory,
]


FILE_ONLY = {"search_attachments", "attach_file", "write_spreadsheet"}
SPEC_KEY = "ai_assistant"
EXTENSION_OPERATIONS = ("create", "update", "submit", "cancel", "delete")


def extension_tools() -> list:
	"""Read tools that installed apps declare in the `ai_assistant_read_tools` hook (SPEC §7.6)."""
	return _hooked("ai_assistant_read_tools", {t.name for t in READ_TOOLS + WRITE_TOOLS})


def extension_write_tools() -> list:
	"""Write tools from the `ai_assistant_write_tools` hook. Each carries `metadata["ai_assistant"]` with
	`operation`, `doctype` and optional `precheck(args)` / `preview(args) -> (headers, rows)` (SPEC §7.6)."""
	taken = {t.name for t in READ_TOOLS + WRITE_TOOLS + extension_tools()}
	found = []
	for item in _hooked("ai_assistant_write_tools", taken):
		spec = (item.metadata or {}).get(SPEC_KEY) or {}
		if spec.get("operation") not in EXTENSION_OPERATIONS or not spec.get("doctype"):
			frappe.log_error(
				f"AI Assistant extension write tool {item.name} has no valid operation and doctype"
			)
			continue
		found.append(item)
	return found


def write_spec(tool_name: str) -> dict | None:
	"""The `metadata["ai_assistant"]` of an extension write tool, else None."""
	item = next((t for t in extension_write_tools() if t.name == tool_name), None)
	return item.metadata[SPEC_KEY] if item else None


MEMORY_ONLY = {"remember", "forget_memory"}


def for_turn(read_only: bool = False, rag: bool = True, files: bool = True, memory: bool = True) -> list:
	"""Tools offered to the model. read_only_mode removes every write tool."""
	writes = [] if read_only else WRITE_TOOLS + extension_write_tools()
	offered = READ_TOOLS + extension_tools() + writes
	return [
		t
		for t in offered
		if (rag or t.name != "search_knowledge")
		and (files or t.name not in FILE_ONLY)
		and (memory or t.name not in MEMORY_ONLY)
	]


def all_tool_names() -> set[str]:
	"""Every tool an agent may list in allowed_tools (core and extension, read and write)."""
	return {t.name for t in READ_TOOLS + WRITE_TOOLS + extension_tools() + extension_write_tools()}


def write_tool_names() -> set[str]:
	return {t.name for t in WRITE_TOOLS + extension_write_tools()}


def _hooked(hook: str, taken: set[str]) -> list:
	"""LangChain tools named by dotted paths in `hook`. A path that does not load, is not a tool, or reuses
	a tool name is skipped and written to the Error Log."""
	taken = set(taken)
	found = []
	for path in frappe.get_hooks(hook) or []:
		try:
			item = frappe.get_attr(path)
		except Exception:
			frappe.log_error(f"AI Assistant extension tool {path} could not be loaded")
			continue
		if not isinstance(item, BaseTool) or item.name in taken:
			frappe.log_error(f"AI Assistant extension tool {path} is not a new LangChain tool")
			continue
		taken.add(item.name)
		found.append(item)
	return found
