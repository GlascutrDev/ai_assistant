"""LangGraph runs checkpoint writes and parallel tool calls in worker threads that share the job's
frappe.db connection (contextvars are copied). One lock keeps queries on that connection serial."""

import threading

LOCK = threading.RLock()
