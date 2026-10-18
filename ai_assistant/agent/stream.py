"""Realtime events to the user's room (SPEC §12): token · step · tool_result · confirmation · done · error."""

import frappe

EVENT = "ai_assistant_stream"


class Publisher:
	"""Sends every model chunk as it arrives. With tools bound, providers already send text in bursts;
	buffering here held each burst's tail until the next one. The browser smooths the display."""

	def __init__(self, conversation: str, user: str, enabled: bool = True):
		self.conversation = conversation
		self.user = user
		self.enabled = enabled

	def token(self, text: str):
		self._send("token", {"text": text})

	def step(self, tool_name: str, args: dict):
		self._send("step", {"tool": tool_name, "args": args})

	def tool_result(self, tool_name: str, status: str, error: str | None = None):
		self._send("tool_result", {"tool": tool_name, "status": status, "error": error})

	def confirmation(self, requests: list[dict]):
		self._send("confirmation", {"requests": requests}, after_commit=True)

	def done(self, status: str):
		self._send("done", {"status": status}, after_commit=True)

	def error(self, message: str):
		self._send("error", {"message": message}, after_commit=True)

	def _send(self, kind: str, data: dict, after_commit: bool = False):
		if not self.enabled:
			return
		frappe.publish_realtime(
			EVENT,
			{"conversation": self.conversation, "type": kind, **data},
			user=self.user,
			after_commit=after_commit,
		)
