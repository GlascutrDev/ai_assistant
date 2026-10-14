"""Make tool results JSON-safe and short (SPEC §7.4)."""

import json
from urllib.parse import quote

import frappe

from ai_assistant.services import settings


def clip(result: dict, max_chars: int | None = None) -> dict:
	"""Drop trailing rows, then cut long text, until the JSON fits `max_tool_result_chars`."""
	max_chars = max_chars or settings.get().max_tool_result_chars or 12000
	result = json.loads(frappe.as_json(result, indent=None))
	if _size(result) <= max_chars:
		return result
	rows = result.get("rows")
	if isinstance(rows, list):
		while rows and _size(result) > max_chars:
			rows.pop()
		result["truncated"] = True
		result["note"] = "Result cut to fit the size limit. Narrow the filters or ask for fewer fields."
		if _size(result) <= max_chars:
			return result
	text = json.dumps(result, default=str)
	return {
		"truncated": True,
		"partial_json": text[: max_chars - 200],
		"note": "Result cut to fit the size limit.",
	}


def desk_link(doctype: str, name: str | None = None) -> str:
	path = "/desk/" + doctype.lower().replace(" ", "-")
	return f"{path}/{quote(str(name), safe='')}" if name else path


def _size(value) -> int:
	return len(json.dumps(value, default=str))
