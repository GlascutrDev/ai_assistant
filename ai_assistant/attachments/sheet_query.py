"""Declarative analysis of one sheet: select, filter, group, aggregate, sort (SPEC §6.8.1). No code runs."""

import datetime
import re
from collections import defaultdict
from statistics import median

import frappe
from frappe import _

from ai_assistant.attachments.sheets import Sheet, plain

OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "contains", "not contains", "starts with", "in", "not in")
OPERATORS += ("is empty", "is not empty")
FUNCTIONS = ("count", "count_distinct", "sum", "avg", "min", "max", "median")
MAX_RESULT_ROWS = 500
NUMBER = re.compile(r"^\(?-?[$€£¥₹]?\s*-?[\d,]*\.?\d+\s*%?\)?$")


def table(sheet: Sheet, header_row: int | None = None) -> tuple[list[str], list[list]]:
	"""(column names, data rows). The header is `header_row` (1-based), else the first non-empty row."""
	rows = sheet.rows
	if header_row:
		index = header_row - 1
	else:
		index = next((i for i, r in enumerate(rows) if any(v is not None for v in r)), 0)
	if index >= len(rows):
		return [], []
	header = rows[index]
	width = max((len(r) for r in rows[index:]), default=0)
	names, seen = [], set()
	for i in range(width):
		raw = header[i] if i < len(header) else None
		name = str(plain(raw)).strip() if raw is not None else f"Column {_letter(i)}"
		while name in seen:
			name += f" ({_letter(i)})"
		seen.add(name)
		names.append(name)
	data = [r + [None] * (width - len(r)) for r in rows[index + 1 :] if any(v is not None for v in r)]
	return names, data


def run(columns: list[str], rows: list[list], spec: dict) -> dict:
	"""spec: columns, filters [{column, op, value}], group_by, aggregates [{fn, column, as}],
	sort [{column, desc}], limit."""
	find = _finder(columns)
	matched = [r for r in rows if all(_keep(r, find, f) for f in spec.get("filters") or [])]
	if spec.get("group_by") or spec.get("aggregates"):
		names, out = _grouped(
			matched, columns, find, spec.get("group_by") or [], spec.get("aggregates") or []
		)
	else:
		picked = [find(c) for c in spec.get("columns") or columns]
		names, out = [columns[i] for i in picked], [[r[i] for i in picked] for r in matched]
	out = _sorted(names, out, spec.get("sort") or [])
	limit = max(1, min(int(spec.get("limit") or 50), MAX_RESULT_ROWS))
	return {
		"columns": names,
		"matched_rows": len(matched),
		"result_rows": len(out),
		"rows": [dict(zip(names, [plain(v) for v in r], strict=True)) for r in out[:limit]],
		"truncated": len(out) > limit,
	}


def profile(columns: list[str], rows: list[list]) -> list[dict]:
	"""Per column: filled count, distinct count, type, and min/max for numbers and dates."""
	out = []
	for i, name in enumerate(columns):
		values = [r[i] for r in rows if r[i] is not None]
		numbers = [n for n in (number(v) for v in values) if n is not None]
		dates = [v for v in values if isinstance(v, datetime.date)]
		kind = "number" if values and len(numbers) == len(values) else "date" if dates else "text"
		item = {
			"column": name,
			"type": kind,
			"filled": len(values),
			"distinct": len({str(v) for v in values}),
		}
		if kind == "number":
			item |= {
				"min": plain(min(numbers)),
				"max": plain(max(numbers)),
				"sum": plain(round(sum(numbers), 6)),
			}
		elif kind == "date":
			item |= {"min": plain(min(dates)), "max": plain(max(dates))}
		out.append(item)
	return out


def number(value) -> float | None:
	"""A number from a cell: numbers, and text such as "1,234.50", "$12", "15%" or "(30)"."""
	if isinstance(value, bool):
		return None
	if isinstance(value, int | float):
		return float(value)
	if not isinstance(value, str) or not NUMBER.match(value.strip()):
		return None
	text = value.strip()
	negative = text.startswith("(") and text.endswith(")")
	cleaned = re.sub(r"[^\d.\-]", "", text)
	try:
		result = float(cleaned)
	except ValueError:
		return None
	result = result / 100 if text.endswith("%") else result
	return -abs(result) if negative else result


def _finder(columns: list[str]):
	lower = {c.lower(): i for i, c in enumerate(columns)}

	def find(name) -> int:
		key = str(name or "").strip()
		if key.lower() in lower:
			return lower[key.lower()]
		if re.fullmatch(r"[A-Za-z]{1,3}", key):
			index = _index(key)
			if index < len(columns):
				return index
		frappe.throw(_("Column {0} does not exist. Columns: {1}").format(key, ", ".join(columns[:60])))

	return find


def _keep(row: list, find, rule: dict) -> bool:
	op = str(rule.get("op") or "=").lower()
	if op not in OPERATORS:
		frappe.throw(_("Unknown filter operator {0}. Use one of: {1}").format(op, ", ".join(OPERATORS)))
	cell, target = row[find(rule.get("column"))], rule.get("value")
	if op in ("is empty", "is not empty"):
		return (cell is None or str(cell).strip() == "") == (op == "is empty")
	if op in ("in", "not in"):
		options = target if isinstance(target, list) else [target]
		return any(_equal(cell, o) for o in options) == (op == "in")
	if op in ("contains", "not contains", "starts with"):
		text, part = str(plain(cell) or "").lower(), str(target or "").lower()
		return text.startswith(part) if op == "starts with" else (part in text) == (op == "contains")
	if op in ("=", "!="):
		return _equal(cell, target) == (op == "=")
	left, right = _comparable(cell, target)
	if left is None or right is None:
		return False
	return {">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right}[op]


def _equal(cell, target) -> bool:
	left, right = _comparable(cell, target)
	if left is not None and right is not None:
		return left == right
	return str(plain(cell) if cell is not None else "").strip().lower() == str(target or "").strip().lower()


def _comparable(cell, target):
	if isinstance(cell, datetime.date):
		try:
			other = datetime.datetime.fromisoformat(str(target))
		except ValueError:
			return None, None
		as_datetime = (
			cell if isinstance(cell, datetime.datetime) else datetime.datetime.combine(cell, datetime.time())
		)
		return as_datetime, other
	return number(cell), number(target)


def _grouped(rows, columns, find, group_by: list, aggregates: list) -> tuple[list[str], list[list]]:
	keys = [find(c) for c in group_by]
	specs = [_aggregate_spec(a, find) for a in aggregates] or [("count", None, "count")]
	groups: dict[tuple, list] = defaultdict(list)
	for r in rows:
		groups[tuple(plain(r[k]) for k in keys)].append(r)
	if not keys and not groups:
		groups[()] = []
	names = [columns[k] for k in keys] + [label for _fn, _col, label in specs]
	out = [
		list(key) + [_apply(fn, col, members) for fn, col, _label in specs] for key, members in groups.items()
	]
	return names, out


def _aggregate_spec(item: dict, find) -> tuple:
	fn = str(item.get("fn") or "count").lower()
	if fn not in FUNCTIONS:
		frappe.throw(_("Unknown aggregate {0}. Use one of: {1}").format(fn, ", ".join(FUNCTIONS)))
	column = find(item["column"]) if item.get("column") else None
	if fn != "count" and column is None:
		frappe.throw(_("Aggregate {0} needs a column.").format(fn))
	label = item.get("as") or (f"{fn}({item['column']})" if column is not None else fn)
	return fn, column, str(label)


def _apply(fn: str, column, rows: list):
	if column is None:
		return len(rows)
	values = [r[column] for r in rows if r[column] is not None and str(r[column]).strip() != ""]
	if fn == "count":
		return len(values)
	if fn == "count_distinct":
		return len({str(plain(v)) for v in values})
	numbers = [n for n in (number(v) for v in values) if n is not None]
	if fn in ("min", "max") and not numbers and values:
		dates = [v for v in values if isinstance(v, datetime.date)]
		return (min if fn == "min" else max)(dates) if dates else None
	if not numbers:
		return None
	result = {"sum": sum, "min": min, "max": max, "median": median}.get(fn, lambda n: sum(n) / len(n))(
		numbers
	)
	return round(result, 6)


def _sorted(names: list[str], rows: list[list], sort: list) -> list[list]:
	find = _finder(names)
	for rule in reversed(sort):
		i = find(rule.get("column"))
		filled = [r for r in rows if r[i] is not None]
		empty = [r for r in rows if r[i] is None]
		rows = sorted(filled, key=lambda r, i=i: _sort_key(r[i]), reverse=bool(rule.get("desc"))) + empty
	return rows


def _sort_key(value):
	n = number(value)
	if n is not None:
		return (0, n, "")
	return (1, 0, str(plain(value)).lower())


def _letter(index: int) -> str:
	letters = ""
	index += 1
	while index:
		index, rem = divmod(index - 1, 26)
		letters = chr(65 + rem) + letters
	return letters


def _index(letters: str) -> int:
	value = 0
	for ch in letters.upper():
		value = value * 26 + ord(ch) - 64
	return value - 1
