"""AI Automation: run the assistant on a schedule or a document event, as its owner (SPEC §6.10).

The owner's permissions apply, every write still waits for the owner's approval, and conditions are Frappe
filters, never code (CLAUDE.md rules 1 and 3)."""

import json
from itertools import pairwise

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from ai_assistant.services import settings
from ai_assistant.services.access import has_access, is_admin

DOCTYPE = "AI Automation"
EVENTS = {
	"after_insert": "After Insert",
	"on_update": "On Update",
	"on_submit": "On Submit",
	"on_cancel": "On Cancel",
}
MAX_PER_USER = 10
MIN_INTERVAL_MINUTES = 15
CACHE_KEY = "ai_assistant:automation_events"
SKIP_FLAGS = ("in_install", "in_migrate", "in_patch", "in_import", "in_setup_wizard", "ai_automation")


def enabled() -> bool:
	return bool(settings.get().automations_enabled)


def validate(doc):
	"""Called from AIAutomation.validate."""
	user = frappe.session.user
	doc.user = doc.user or user
	if doc.user != user and not is_admin(user):
		frappe.throw(_("You can only change your own automations."), frappe.PermissionError)
	if not has_access(doc.user):
		frappe.throw(_("{0} cannot use the AI Assistant.").format(doc.user), frappe.PermissionError)
	if doc.is_new() and frappe.db.count(DOCTYPE, {"user": doc.user}) >= MAX_PER_USER:
		frappe.throw(_("At most {0} automations per user.").format(MAX_PER_USER))
	if doc.agent:
		from ai_assistant.services import agents

		agents.load(doc.agent, doc.user)
	if doc.event == "Schedule":
		check_cron(doc.cron)
		doc.document_type = doc.doc_event = doc.filters_json = None
	else:
		_check_document_event(doc)
		doc.cron = None


def check_cron(cron: str | None):
	from croniter import croniter

	if not cron or not croniter.is_valid(cron.strip()):
		frappe.throw(_("Give a valid cron schedule, for example 0 9 * * 1-5."))
	times = croniter(cron.strip(), now_datetime())
	runs = [times.get_next(type(now_datetime())) for _i in range(6)]
	if min((b - a).total_seconds() for a, b in pairwise(runs)) < MIN_INTERVAL_MINUTES * 60:
		frappe.throw(_("An automation can run at most every {0} minutes.").format(MIN_INTERVAL_MINUTES))


def is_due(doc, now=None) -> bool:
	"""True when a cron time has passed since the last run (or since the automation was saved)."""
	from croniter import croniter

	now = now or now_datetime()
	since = get_datetime(doc.last_run_at or doc.modified)
	return croniter(doc.cron, since).get_next(type(now)) <= now


def due_schedules(now=None) -> list[str]:
	if not enabled():
		return []
	rows = frappe.get_all(
		DOCTYPE,
		filters={"enabled": 1, "event": "Schedule"},
		fields=["name", "cron", "last_run_at", "modified"],
	)
	return [r.name for r in rows if r.cron and is_due(r, now)]


def run_due():
	"""Scheduler (every minute): queue each due scheduled automation once."""
	for name in due_schedules():
		frappe.db.set_value(DOCTYPE, name, "last_run_at", now_datetime(), update_modified=False)
		_enqueue(name)


def on_doc_event(doc, method=None):
	"""doc_events["*"]: queue the automations that watch this DocType and event, when the record matches."""
	if any(frappe.flags.get(f) for f in SKIP_FLAGS) or doc.doctype.startswith("AI "):
		return
	event = EVENTS.get(method)
	watchers = _watchers().get(doc.doctype, {}).get(event) if event else None
	if not watchers or not enabled():
		return
	for name in watchers:
		row = frappe.db.get_value(DOCTYPE, name, ["user", "filters_json"], as_dict=True)
		if row and matches(doc.doctype, doc.name, row.filters_json, row.user):
			_enqueue(name, doctype=doc.doctype, docname=doc.name)


def matches(doctype: str, name: str, filters_json: str | None, user: str) -> bool:
	"""The owner can read the record and it matches the filters (read as the owner)."""
	if not frappe.has_permission(doctype, "read", doc=name, user=user):
		return False
	filters = json.loads(filters_json) if filters_json else {}
	return bool(frappe.get_list(doctype, filters={**filters, "name": name}, limit=1, user=user))


def recent_runs(name: str) -> int:
	return frappe.db.count(
		"AI Conversation", {"automation": name, "creation": [">", add_to_date(now_datetime(), hours=-1)]}
	)


def clear_cache():
	frappe.cache.delete_value(CACHE_KEY)


def _watchers() -> dict:
	"""{doctype: {event label: [automation]}} of enabled document-event automations, cached."""
	cached = frappe.cache.get_value(CACHE_KEY)
	if cached is not None:
		return cached
	out: dict = {}
	for r in frappe.get_all(
		DOCTYPE,
		filters={"enabled": 1, "event": "Document Event"},
		fields=["name", "document_type", "doc_event"],
	):
		out.setdefault(r.document_type, {}).setdefault(r.doc_event, []).append(r.name)
	frappe.cache.set_value(CACHE_KEY, out)
	return out


def _check_document_event(doc):
	from ai_assistant.tools import guard

	if not doc.document_type or doc.doc_event not in EVENTS.values():
		frappe.throw(_("Choose the document type and the event."))
	guard.require_doctype(doc.document_type)
	if settings.is_blocked(doc.document_type) or frappe.get_meta(doc.document_type).issingle:
		frappe.throw(_("Automations cannot watch {0}.").format(doc.document_type))
	if not frappe.has_permission(doc.document_type, "read", user=doc.user):
		frappe.throw(_("You cannot read {0}.").format(doc.document_type), frappe.PermissionError)
	if doc.doc_event in ("On Submit", "On Cancel") and not frappe.get_meta(doc.document_type).is_submittable:
		frappe.throw(_("{0} is not submittable.").format(doc.document_type))
	if doc.filters_json:
		try:
			filters = json.loads(doc.filters_json)
		except ValueError:
			frappe.throw(_("Filters must be JSON."))
		if not isinstance(filters, dict | list):
			frappe.throw(_("Filters must be an object or a list."))
		frappe.get_list(doc.document_type, filters=filters, limit=1, user=doc.user)


def _enqueue(name: str, doctype: str | None = None, docname: str | None = None):
	frappe.enqueue(
		"ai_assistant.services.automation_run.run",
		queue="long",
		timeout=1800,
		job_id=f"ai-automation-{name}-{docname or 'schedule'}",
		deduplicate=True,
		enqueue_after_commit=True,
		now=bool(frappe.in_test),
		automation=name,
		doctype=doctype,
		docname=docname,
	)
