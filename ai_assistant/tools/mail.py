"""send_email (SPEC §7.2): an email from the user, optionally on a record's timeline. Always confirmed."""

import frappe
from frappe import _
from frappe.core.doctype.communication.email import make
from frappe.utils import escape_html, validate_email_address
from langchain.tools import ToolRuntime, tool

from ai_assistant.services import attachments
from ai_assistant.tools import base, files, guard

MAX_RECIPIENTS = 20
MAX_FILES = 5


@tool
def send_email(
	recipients: list[str],
	subject: str,
	message: str,
	cc: list[str] | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	files_to_attach: list[str] | None = None,
	runtime: ToolRuntime = None,
) -> dict:
	"""Send an email from the user. message is plain text. With reference_doctype and reference_name the
	email is linked to that record and shows on its timeline. files_to_attach: chat attachment ids or File
	names the user can read (at most 5). The user sees the full email and confirms before it is sent."""
	args = {
		"recipients": recipients,
		"subject": subject,
		"message": message,
		"cc": cc,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"files_to_attach": files_to_attach,
	}
	return base.execute(
		"send_email",
		lambda: _send(args, runtime),
		operation="email",
		doctype=reference_doctype or "Communication",
		name=reference_name,
		args=args,
		runtime=runtime,
		savepoint=True,
	)


def precheck(args: dict):
	"""See ai_assistant.tools.preview.precheck."""
	_checked(args)


def _send(args: dict, runtime) -> dict:
	recipients, cc, file_names = _checked(args, runtime)
	result = make(
		doctype=args.get("reference_doctype") or None,
		name=args.get("reference_name") or None,
		subject=args["subject"],
		content=escape_html(args["message"]).replace("\n", "<br>"),
		recipients=recipients,
		cc=cc or None,
		send_email=True,
		attachments=file_names or None,
	)
	return {"result": "sent", "communication": result.get("name"), "recipients": recipients, "cc": cc}


def _checked(args: dict, runtime=None) -> tuple[list[str], list[str], list[str]]:
	"""(recipients, cc, File names). Raises unless the user may send this email."""
	doctype, name = args.get("reference_doctype"), args.get("reference_name")
	if doctype or name:
		if not (doctype and name):
			frappe.throw(_("Give both reference_doctype and reference_name, or neither."))
		guard.check(doctype, "email", name)
	else:
		guard.check("Communication", "create")
	if not str(args.get("subject") or "").strip() or not str(args.get("message") or "").strip():
		frappe.throw(_("The email needs a subject and a message."))
	recipients, cc = _addresses(args.get("recipients"), True), _addresses(args.get("cc"), False)
	if len(recipients) + len(cc) > MAX_RECIPIENTS:
		frappe.throw(_("At most {0} recipients.").format(MAX_RECIPIENTS))
	return recipients, cc, _files(args.get("files_to_attach"), runtime)


def _addresses(value, required: bool) -> list[str]:
	if value in (None, []) and not required:
		return []
	if not isinstance(value, list) or not value:
		frappe.throw(_("Give the recipients as a list of email addresses."))
	out = []
	for address in value:
		if not validate_email_address(str(address).strip()):
			frappe.throw(_("{0} is not a valid email address.").format(address))
		out.append(str(address).strip())
	return list(dict.fromkeys(out))


def _files(value, runtime) -> list[str]:
	if not value:
		return []
	if not isinstance(value, list) or len(value) > MAX_FILES:
		frappe.throw(_("Attach at most {0} files.").format(MAX_FILES))
	out = []
	for item in value:
		files.file_content(item, runtime)
		out.append(attachments.load_own(item).file if attachments.exists(item) else item)
	return out
