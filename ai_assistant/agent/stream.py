"""Realtime events to the user's room (SPEC §12): token · step · tool_result · confirmation · done · error."""

import time

import frappe

EVENT = "ai_assistant_stream"
TOKEN_INTERVAL = 0.1


class Publisher:
	def __init__(self, conversation: str, user: str, enabled: bool = True):
		self.conversation = conversation
		self.user = user
		self.enabled = enabled
		self._buffer = ""
		self._last_flush = 0.0

	def token(self, text: str):
		self._buffer += text
		if time.monotonic() - self._last_flush >= TOKEN_INTERVAL:
			self.flush()

	def flush(self):
		if self._buffer:
			self._send("token", {"text": self._buffer})
			self._buffer = ""
		self._last_flush = time.monotonic()

	def step(self, tool_name: str, args: dict):
		self.flush()
		self._send("step", {"tool": tool_name, "args": args})

	def tool_result(self, tool_name: str, status: str):
		self._send("tool_result", {"tool": tool_name, "status": status})

	def confirmation(self, requests: list[dict]):
		self.flush()
		self._send("confirmation", {"requests": requests}, after_commit=True)

	def done(self, status: str):
		self.flush()
		self._send("done", {"status": status}, after_commit=True)

	def error(self, message: str):
		self.flush()
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
