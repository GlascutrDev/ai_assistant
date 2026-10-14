"""Run a tool body with outcome mapping, the audit row, and result clipping."""

import time
from collections.abc import Callable

import frappe
from frappe import _
from frappe.utils import strip_html

from ai_assistant.agent import context as turn
from ai_assistant.persistence import dblock
from ai_assistant.services import audit
from ai_assistant.tools import serialize
from ai_assistant.tools.guard import BlockedDocTypeError


def execute(
	tool_name: str,
	body: Callable[[], dict],
	*,
	operation: str = "read",
	doctype: str | None = None,
	name: str | None = None,
	args: dict | None = None,
	runtime=None,
	savepoint: bool = False,
) -> dict:
	with dblock.locked():
		return _execute(tool_name, body, operation, doctype, name, args, runtime, savepoint)


def _execute(tool_name, body, operation, doctype, name, args, runtime, savepoint) -> dict:
	ctx = turn.of(runtime)
	start = time.monotonic()
	outcome, error = "ok", None
	sp = f"ai_tool_{frappe.generate_hash(length=8)}" if savepoint else None
	if sp:
		frappe.db.savepoint(sp)
	try:
		result = body()
	except BlockedDocTypeError as e:
		outcome, error, result = "blocked_doctype", str(e), {"error": str(e), "outcome": "blocked_doctype"}
	except frappe.PermissionError as e:
		message = _message(e) or _("Permission denied.")
		outcome, error, result = (
			"permission_denied",
			message,
			{"error": message, "outcome": "permission_denied"},
		)
	except (frappe.ValidationError, frappe.DoesNotExistError) as e:
		message = _message(e)
		outcome, error, result = "validation_error", message, {"error": message}
	except Exception as e:
		frappe.log_error(f"AI Assistant tool {tool_name} failed")
		outcome, error, result = "error", f"{type(e).__name__}: {e}"[:500], {"error": _("The tool failed.")}
	finally:
		frappe.clear_messages()
	if sp and outcome != "ok":
		frappe.db.rollback(save_point=sp)
	audit.tool_call(
		tool_name=tool_name,
		outcome=outcome,
		operation=operation,
		target_doctype=doctype,
		target_name=name,
		args=args,
		error=error,
		duration_ms=int((time.monotonic() - start) * 1000),
		conversation=ctx.conversation,
	)
	return serialize.clip(result)


def _message(e: Exception) -> str:
	text = str(e) or (frappe.local.message_log and frappe.local.message_log[-1]) or ""
	if isinstance(text, dict):
		text = text.get("message", "")
	return strip_html(str(text))[:1000]
