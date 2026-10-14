"""DB access from LangGraph worker threads.

LangGraph runs checkpoint writes and tool calls in worker threads. Some of them do not inherit the
job's frappe.local (a ContextVar), and all of them share its DB connection. `locked()` binds the
job's frappe.local in the current thread and serializes queries on the shared connection.
"""

import threading
from contextlib import contextmanager

from frappe.utils.local import _contextvar

LOCK = threading.RLock()
_state = {"local": None}


def bind_turn():
	"""Remember the calling thread's frappe.local for worker threads. Call before running a graph."""
	_state["local"] = _contextvar.get(None)


@contextmanager
def locked():
	with LOCK:
		current = _contextvar.get(None)
		if current is not None or _state["local"] is None:
			yield
			return
		token = _contextvar.set(_state["local"])
		try:
			yield
		finally:
			_contextvar.reset(token)
