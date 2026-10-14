"""LangSmith tracing from Settings, per site, never from environment variables (SPEC §11.1)."""

import frappe

from ai_assistant.services import settings

_clients: dict[tuple, object] = {}


def tracer(ctx, purpose: str = "agent"):
	"""A LangChainTracer for one turn, or None when tracing is off."""
	client = get_client()
	if not client:
		return None
	from langchain_core.tracers.langchain import LangChainTracer

	return LangChainTracer(
		project_name=project_name(),
		client=client,
		tags=[frappe.local.site, ctx.model_profile or "", purpose],
		metadata={
			"user": ctx.user,
			"conversation": ctx.conversation or "",
			"model_profile": ctx.model_profile or "",
		},
	)


def get_client():
	conf = settings.get()
	if not conf.langsmith_enabled:
		return None
	key = conf.get_password("langsmith_api_key", raise_exception=False)
	if not key:
		return None
	cache_key = (frappe.local.site, str(conf.modified))
	if cache_key not in _clients:
		_clients.clear()
		_clients[cache_key] = _build_client(
			key, conf.langsmith_endpoint or None, bool(conf.langsmith_hide_io)
		)
	return _clients[cache_key]


def project_name() -> str:
	return settings.get().langsmith_project or f"ai_assistant-{frappe.local.site}"


def root_run_id(turn_tracer) -> str | None:
	run = getattr(turn_tracer, "latest_run", None) if turn_tracer else None
	return str(run.id) if run else None


def flush(turn_tracer):
	if turn_tracer:
		try:
			turn_tracer.wait_for_futures()
			turn_tracer.client.flush()
		except Exception:
			frappe.log_error("AI Assistant LangSmith flush failed")


def _build_client(api_key: str, api_url: str | None, hide_io: bool):
	from langsmith import Client

	return Client(api_key=api_key, api_url=api_url, hide_inputs=hide_io, hide_outputs=hide_io)
