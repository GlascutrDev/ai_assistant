"""Daily per-user token and monthly per-site cost limits (SPEC §9)."""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, get_first_day, get_last_day, nowdate

from ai_assistant.services import settings

USER_PURPOSES_EXCLUDED = ("evaluation", "test")


class BudgetExceededError(frappe.ValidationError):
	pass


def assert_available(user: str | None = None):
	user = user or frappe.session.user
	limit = settings.get().user_daily_token_limit
	if limit and tokens_today(user) >= limit:
		frappe.throw(_("Daily AI limit reached. It resets at midnight."), BudgetExceededError)
	assert_site_budget()


def assert_site_budget():
	limit = flt(settings.get().site_monthly_cost_limit)
	if limit and cost_this_month() >= limit:
		frappe.throw(
			_("The site's monthly AI budget is used up. Contact your administrator."), BudgetExceededError
		)


def tokens_left_today(user: str | None = None) -> int | None:
	limit = settings.get().user_daily_token_limit
	if not limit:
		return None
	return max(limit - tokens_today(user or frappe.session.user), 0)


def tokens_today(user: str) -> int:
	key = _user_key(user)
	value = frappe.cache.get_value(key)
	if value is None:
		log = frappe.qb.DocType("AI Usage Log")
		value = (
			frappe.qb.from_(log)
			.select(Coalesce(Sum(log.input_tokens + log.output_tokens), 0))
			.where((log.user == user) & (log.date == nowdate()) & log.purpose.notin(USER_PURPOSES_EXCLUDED))
		).run()[0][0]
		frappe.cache.set_value(key, int(value), expires_in_sec=86400)
	return int(value)


def cost_this_month() -> float:
	key = _site_key()
	value = frappe.cache.get_value(key)
	if value is None:
		log = frappe.qb.DocType("AI Usage Log")
		today = nowdate()
		value = (
			frappe.qb.from_(log)
			.select(Coalesce(Sum(log.cost), 0))
			.where(log.date.between(get_first_day(today), get_last_day(today)))
		).run()[0][0]
		frappe.cache.set_value(key, flt(value), expires_in_sec=86400)
	return flt(value)


def add(user: str, tokens: int, cost: float, purpose: str):
	"""Invalidate the cached totals; the next check recomputes them from AI Usage Log."""
	frappe.cache.delete_value(_user_key(user))
	frappe.cache.delete_value(_site_key())


def _user_key(user: str) -> str:
	return f"ai_assistant:tokens:{user}:{nowdate()}"


def _site_key() -> str:
	return f"ai_assistant:cost:{nowdate()[:7]}"
