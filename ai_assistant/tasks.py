"""Scheduled jobs (SPEC §5). Thin: delegate to services."""

import frappe

from ai_assistant.services import actions


def expire_action_requests():
	actions.expire_stale()
	frappe.db.commit()
