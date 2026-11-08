"""Memory tools (SPEC §6.9, §7.2): remember, forget_memory. Each save is confirmed like every write."""

import frappe
from frappe import _
from langchain.tools import ToolRuntime, tool

from ai_assistant.agent import context as turn
from ai_assistant.services import memory
from ai_assistant.tools import base


@tool
def remember(content: str, memory_id: str | None = None, runtime: ToolRuntime = None) -> dict:
	"""Save a short fact about this user or their work to keep for later conversations (for example a
	preference, their warehouse, how they want reports). Only when the user asks you to remember it, or
	clearly states a lasting preference. Never save secrets or passwords. With memory_id, change that
	memory instead of adding one. The user confirms first."""
	args = {"content": content, "memory_id": memory_id}
	conversation = turn.of(runtime).conversation
	return base.execute(
		"remember",
		lambda: memory.remember(content, memory_id, conversation),
		operation="update" if memory_id else "create",
		doctype=memory.DOCTYPE,
		name=memory_id,
		args=args,
		runtime=runtime,
		savepoint=True,
	)


@tool
def forget_memory(memory_id: str, runtime: ToolRuntime = None) -> dict:
	"""Forget one of this user's saved memories (by its id in the Memories list). The user confirms first."""
	return base.execute(
		"forget_memory",
		lambda: memory.forget(memory_id),
		operation="delete",
		doctype=memory.DOCTYPE,
		name=memory_id,
		args={"memory_id": memory_id},
		runtime=runtime,
		savepoint=True,
	)


def precheck(tool_name: str, args: dict):
	"""See ai_assistant.tools.preview.precheck."""
	if not memory.enabled():
		frappe.throw(_("Memory is turned off in AI Assistant Settings."))
	if args.get("memory_id"):
		memory.own(args["memory_id"])
	if tool_name == "remember":
		content = str(args.get("content") or "").strip()
		if not content or len(content) > memory.MAX_CHARS:
			frappe.throw(_("A memory has 1 to {0} characters.").format(memory.MAX_CHARS))


def preview_rows(tool_name: str, args: dict) -> tuple[list[str], list[tuple]]:
	current = memory.own(args["memory_id"]).content if args.get("memory_id") else None
	if tool_name == "forget_memory":
		return ["Forget memory"], [(current,)]
	return ["Memory", "Now", "New"], [(args.get("memory_id") or _("new"), current, args.get("content"))]
