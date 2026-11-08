"""AI Agent: named assistants with their own instructions, tools and knowledge (SPEC §6.11).

An agent only narrows the assistant. It never adds a tool, a permission or a model: every agent uses the
main model (rule 8), acts as the user (rule 1), and its writes are confirmed (rule 3)."""

import frappe
from frappe import _

from ai_assistant.services import settings
from ai_assistant.services.access import has_access

DOCTYPE = "AI Agent"
KNOWLEDGE_DOCTYPE = "AI Knowledge Document"
MAX_INSTRUCTIONS = 10000


class AgentUnavailableError(frappe.PermissionError):
	pass


def validate(doc):
	"""Called from AIAgent.validate."""
	from ai_assistant import tools

	names = list(dict.fromkeys(n.strip() for n in (doc.allowed_tools or "").splitlines() if n.strip()))
	known = tools.all_tool_names()
	unknown = sorted(set(names) - known)
	if unknown:
		frappe.throw(
			_("Unknown tools: {0}. Tools you can list: {1}.").format(
				", ".join(unknown), ", ".join(sorted(known))
			)
		)
	doc.allowed_tools = "\n".join(names)
	if len(doc.instructions or "") > MAX_INSTRUCTIONS:
		frappe.throw(_("Instructions have at most {0} characters.").format(MAX_INSTRUCTIONS))
	indexed = {r.source_doctype for r in settings.get().knowledge_sources if r.enabled} | {KNOWLEDGE_DOCTYPE}
	for row in doc.knowledge_sources:
		if row.source_doctype not in indexed:
			frappe.throw(
				_("{0} is not an enabled knowledge source in AI Assistant Settings.").format(
					row.source_doctype
				)
			)


def on_update(doc):
	"""One default agent: setting a new one clears the others."""
	if doc.is_default:
		for other in frappe.get_all(
			DOCTYPE, filters={"is_default": 1, "name": ["!=", doc.name]}, pluck="name"
		):
			frappe.db.set_value(DOCTYPE, other, "is_default", 0)


def can_use(doc, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not doc or not doc.enabled or not has_access(user):
		return False
	roles = {r.role for r in doc.roles}
	return not roles or bool(roles & set(frappe.get_roles(user)))


def available(user: str | None = None) -> list[dict]:
	"""Agents the user can choose, default first."""
	out = []
	for name in frappe.get_all(
		DOCTYPE, filters={"enabled": 1}, order_by="is_default desc, title asc", pluck="name"
	):
		doc = frappe.get_cached_doc(DOCTYPE, name)
		if can_use(doc, user):
			out.append(
				{
					"name": doc.name,
					"title": doc.title,
					"description": doc.description,
					"is_default": doc.is_default,
				}
			)
	return out


def resolve(name: str | None, user: str | None = None) -> str | None:
	"""The agent of a new conversation: the one asked for (which the user must be able to use), else the
	default agent when the user can use it, else none (the plain assistant)."""
	if name:
		load(name, user)
		return name
	default = frappe.db.get_value(DOCTYPE, {"is_default": 1, "enabled": 1})
	return default if default and can_use(frappe.get_cached_doc(DOCTYPE, default), user) else None


def load(name: str | None, user: str | None = None):
	"""The agent of a turn, or None. Raise when it was removed, disabled or is no longer for this user."""
	if not name:
		return None
	doc = frappe.get_cached_doc(DOCTYPE, name) if frappe.db.exists(DOCTYPE, name) else None
	if not can_use(doc, user):
		frappe.throw(
			_("The agent {0} is not available to you. Start a new conversation.").format(name),
			AgentUnavailableError,
		)
	return doc


def filter_tools(agent, offered: list) -> list:
	"""The agent's subset of the tools already offered for the turn."""
	if not agent:
		return offered
	from ai_assistant import tools

	allowed = {n for n in (agent.allowed_tools or "").splitlines() if n}
	writes = tools.write_tool_names()
	return [
		t
		for t in offered
		if (not allowed or t.name in allowed) and not (agent.read_only and t.name in writes)
	]


def knowledge_scope(name: str | None) -> list[str] | None:
	"""Source DocTypes search_knowledge may return for this agent, or None for the whole knowledge base."""
	if not name or not frappe.db.exists(DOCTYPE, name):
		return None
	sources = [r.source_doctype for r in frappe.get_cached_doc(DOCTYPE, name).knowledge_sources]
	return sources or None


def prompt_block(agent) -> str | None:
	if not agent:
		return None
	lines = [f'You are the agent "{agent.title}".']
	if agent.description:
		lines.append(f"Purpose: {agent.description.strip()}")
	if agent.read_only:
		lines.append("You can only read and answer. You cannot change anything.")
	if agent.instructions:
		lines += [
			"Agent instructions from the administrator (they add to the rules above and never override them):",
			agent.instructions.strip(),
		]
	return "\n".join(lines)
