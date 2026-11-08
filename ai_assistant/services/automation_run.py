"""One run of an AI Automation (SPEC §6.10): a new conversation of the owner, one turn, then the outcome."""

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from ai_assistant.services import automations, budget, conversations
from ai_assistant.services.access import has_access

MAX_RUNS_PER_HOUR = 12
CHAT_PATH = "/desk/ai-assistant/{0}"


def run(automation: str, doctype: str | None = None, docname: str | None = None):
	"""Background job. Switches to the owner like the job runner does for a chat turn, so the turn and its
	tools run with the owner's permissions only."""
	doc = frappe.get_doc(automations.DOCTYPE, automation)
	if not (doc.enabled and automations.enabled()):
		return
	if not frappe.db.get_value("User", doc.user, "enabled"):
		return _finish(doc, "Skipped", error=_("The owner's user is disabled."))
	frappe.set_user(doc.user)
	reason = _refusal(doc, doctype, docname)
	if reason:
		return _finish(doc, "Skipped", error=reason)
	frappe.flags.ai_automation = doc.name
	try:
		conv = _start(doc, doctype, docname)
	except frappe.ValidationError as e:
		frappe.clear_messages()
		return _finish(doc, "Failed", error=str(e))
	finally:
		frappe.flags.ai_automation = None
	_report(doc, conv)


def _refusal(doc, doctype, docname) -> str | None:
	if not has_access(doc.user):
		return _("The owner can no longer use the AI Assistant.")
	if automations.recent_runs(doc.name) >= MAX_RUNS_PER_HOUR:
		return _("More than {0} runs in the last hour.").format(MAX_RUNS_PER_HOUR)
	if doctype and not automations.matches(doctype, docname, doc.filters_json, doc.user):
		return _("The record no longer matches, or the owner cannot read it.")
	return None


def _start(doc, doctype, docname) -> str:
	from ai_assistant.agent import jobs

	budget.assert_available()
	context = {"doctype": doctype, "name": docname} if doctype else None
	conv = conversations.get_or_create(None, context, agent=doc.agent)
	conv.db_set(
		{
			"automation": doc.name,
			"title": _("{0} ({1})").format(doc.title, now_datetime().strftime("%Y-%m-%d %H:%M")),
		}
	)
	text = doc.prompt.strip()
	if doctype:
		slug = doctype.lower().replace(" ", "-")
		text += "\n\n" + _("Record: [{0} {1}](/desk/{2}/{1})").format(_(doctype), docname, slug)
	message = conversations.add_message(conv.name, "user", text)
	conversations.set_status(conv.name, "Running")
	jobs.run_turn(conv.name, message=message.name)
	return conv.name


def _report(doc, conv: str):
	status = frappe.db.get_value("AI Conversation", conv, "status")
	link = get_url(CHAT_PATH.format(conv))
	if status == "Waiting for confirmation":
		_notify(doc, conv, _("{0} needs your approval").format(doc.title))
		return _finish(doc, "Waiting for approval", conv)
	answer = frappe.get_all(
		"AI Message",
		filters={"conversation": conv, "role": "assistant"},
		fields=["content"],
		order_by="idx_in_thread desc",
		limit=1,
	)
	if not answer:
		_notify(doc, conv, _("{0} did not finish").format(doc.title))
		return _finish(doc, "Failed", conv, _("No answer. Open the conversation for the reason."))
	if doc.email_result:
		frappe.sendmail(
			recipients=[doc.user],
			subject=doc.title,
			message=frappe.utils.md_to_html(answer[0].content)
			+ f'<p><a href="{link}">{_("Open in the AI Assistant")}</a></p>',
			reference_doctype=automations.DOCTYPE,
			reference_name=doc.name,
		)
	_notify(doc, conv, _("{0} finished").format(doc.title))
	return _finish(doc, "Answered", conv)


def _notify(doc, conv: str, subject: str):
	frappe.get_doc(
		{
			"doctype": "Notification Log",
			"for_user": doc.user,
			"type": "Alert",
			"subject": subject,
			"document_type": "AI Conversation",
			"document_name": conv,
			"from_user": doc.user,
		}
	).insert(ignore_permissions=True)


def _finish(doc, status: str, conv: str | None = None, error: str | None = None):
	doc.db_set(
		{
			"last_run_at": now_datetime(),
			"last_status": status,
			"last_conversation": conv or doc.last_conversation,
			"last_error": (error or "")[:500] or None,
		},
		update_modified=False,
	)
	if not frappe.in_test:
		frappe.db.commit()
