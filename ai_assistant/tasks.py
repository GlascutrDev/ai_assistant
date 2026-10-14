"""Scheduled jobs (SPEC §5). Thin: delegate to services."""

import frappe

from ai_assistant.services import actions


def expire_action_requests():
	actions.expire_stale()
	frappe.db.commit()


def reindex_changed_sources():
	from ai_assistant.rag import indexer

	indexer.reindex_changed_sources()
	frappe.db.commit()


def purge_old_conversations():
	from ai_assistant.services import attachments

	attachments.purge_old()
	frappe.db.commit()
