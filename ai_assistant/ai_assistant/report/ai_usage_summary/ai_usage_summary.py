# Copyright (c) 2026, Glascutr Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, nowdate

GROUPS = {"User": "user", "Model": "profile_id", "Day": "date", "Purpose": "purpose"}


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	group = GROUPS.get(filters.group_by or "User", "user")
	return columns(group), data(filters, group)


def columns(group: str) -> list[dict]:
	first = {
		"user": {
			"fieldname": "user",
			"label": _("User"),
			"fieldtype": "Link",
			"options": "User",
			"width": 220,
		},
		"profile_id": {
			"fieldname": "profile_id",
			"label": _("Model Profile"),
			"fieldtype": "Data",
			"width": 160,
		},
		"date": {"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 110},
		"purpose": {"fieldname": "purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 120},
	}[group]
	return [
		first,
		{"fieldname": "calls", "label": _("Calls"), "fieldtype": "Int", "width": 90},
		{"fieldname": "input_tokens", "label": _("Input Tokens"), "fieldtype": "Int", "width": 130},
		{"fieldname": "output_tokens", "label": _("Output Tokens"), "fieldtype": "Int", "width": 130},
		{"fieldname": "audio_seconds", "label": _("Audio Seconds"), "fieldtype": "Float", "width": 120},
		{"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 120},
	]


def data(filters, group: str) -> list[dict]:
	log = frappe.qb.DocType("AI Usage Log")
	field = log[group]
	query = (
		frappe.qb.from_(log)
		.select(
			field.as_(group),
			Count("*").as_("calls"),
			Sum(log.input_tokens).as_("input_tokens"),
			Sum(log.output_tokens).as_("output_tokens"),
			Sum(log.audio_seconds).as_("audio_seconds"),
			Sum(log.cost).as_("cost"),
		)
		.where(log.date.between(filters.from_date or add_days(nowdate(), -30), filters.to_date or nowdate()))
		.groupby(field)
		.orderby(Sum(log.cost), order=frappe.qb.desc)
	)
	for name in ("user", "profile_id", "purpose"):
		if filters.get(name):
			query = query.where(log[name] == filters.get(name))
	return query.run(as_dict=True)
