"""Tool registry. Every tool in WRITE_TOOLS is interrupted for confirmation (CLAUDE.md rule 3)."""

from ai_assistant.tools.meta import describe_doctype, find_doctypes
from ai_assistant.tools.read import aggregate, count_documents, get_document, list_documents, search_links
from ai_assistant.tools.reports import run_report

READ_TOOLS = [
	find_doctypes,
	describe_doctype,
	list_documents,
	count_documents,
	aggregate,
	get_document,
	run_report,
	search_links,
]

WRITE_TOOLS = []


def for_turn(read_only: bool = False) -> list:
	"""Tools offered to the model. read_only_mode removes every write tool."""
	return READ_TOOLS + ([] if read_only else WRITE_TOOLS)


def write_tool_names() -> set[str]:
	return {t.name for t in WRITE_TOOLS}
