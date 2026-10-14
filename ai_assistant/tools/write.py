"""Write tools (SPEC §7.2). Each one is interrupted for confirmation before it runs."""

import frappe
from frappe.utils import escape_html


def target_of(tool_name: str, args: dict) -> tuple[str | None, str | None]:
	doctype = args.get("doctype")
	name = args.get("name")
	return (doctype if isinstance(doctype, str) else None), (str(name)[:140] if name else None)


def preview_html(tool_name: str, args: dict) -> str:
	"""A table of the actual arguments the tool will run with (SPEC §7.4)."""
	rows = "".join(
		f"<tr><td>{escape_html(str(k))}</td><td>{escape_html(frappe.as_json(v, indent=None)[:500])}</td></tr>"
		for k, v in args.items()
	)
	return f'<table class="table table-bordered table-sm"><tbody>{rows}</tbody></table>'
