"""AI Audit Log: one row per tool call, no document content (SPEC §10)."""

import hashlib
import json

import frappe

from ai_assistant.services import catalog


def tool_call(
	*,
	tool_name: str,
	outcome: str,
	operation: str | None = None,
	target_doctype: str | None = None,
	target_name: str | None = None,
	args: dict | None = None,
	error: str | None = None,
	duration_ms: int = 0,
	conversation: str | None = None,
):
	frappe.get_doc(
		{
			"doctype": "AI Audit Log",
			"user": frappe.session.user,
			"conversation": conversation,
			"tool_name": tool_name,
			"operation": operation,
			"outcome": outcome,
			"target_doctype": target_doctype if catalog.is_doctype(target_doctype) else None,
			"target_name": (target_name or "")[:140] or None,
			"args_hash": args_hash(args),
			"duration_ms": duration_ms,
			"error": (error or "")[:1000] or None,
		}
	).insert(ignore_permissions=True)


def args_hash(args: dict | None) -> str | None:
	if not args:
		return None
	return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:32]
