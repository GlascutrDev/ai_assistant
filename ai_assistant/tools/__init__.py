"""Tool registry. Every tool in WRITE_TOOLS is interrupted for confirmation (CLAUDE.md rule 3)."""

from ai_assistant.tools.knowledge import search_knowledge
from ai_assistant.tools.meta import describe_doctype, find_doctypes
from ai_assistant.tools.read import aggregate, count_documents, get_document, list_documents, search_links
from ai_assistant.tools.reports import run_report
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
]


def for_turn(read_only: bool = False, rag: bool = True) -> list:
	"""Tools offered to the model. read_only_mode removes every write tool."""
	reads = [t for t in READ_TOOLS if rag or t.name != "search_knowledge"]
	return reads + ([] if read_only else WRITE_TOOLS)


def write_tool_names() -> set[str]:
	return {t.name for t in WRITE_TOOLS}
