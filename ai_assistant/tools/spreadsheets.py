"""Spreadsheet tools (SPEC §6.8.1, §7.1, §7.2): inspect_spreadsheet, query_spreadsheet, write_spreadsheet."""

import os
import re

import frappe
from frappe import _
from langchain.tools import ToolRuntime, tool

from ai_assistant.agent import context as turn
from ai_assistant.attachments import sheet_query, sheets
from ai_assistant.services import attachments, conversations
from ai_assistant.tools import base, files, guard

SAMPLE_ROWS = 5
MAX_WRITE_CELLS = 200_000
CELL = re.compile(r"^[A-Z]{1,3}[1-9]\d{0,6}$")


@tool
def inspect_spreadsheet(file: str, runtime: ToolRuntime = None) -> dict:
	"""Describe a spreadsheet (.xlsx, .xlsm, .xls, .csv, .tsv): every sheet with its row count, column
	names, a profile per column (type, filled, distinct, min/max/sum) and the first rows. Use it before
	query_spreadsheet. file: a chat attachment id, or the File name of a file on a record you can read."""
	return base.execute(
		"inspect_spreadsheet",
		lambda: _inspect(file, runtime),
		doctype="File",
		args={"file": file},
		runtime=runtime,
	)


@tool
def query_spreadsheet(
	file: str,
	sheet: str | None = None,
	columns: list[str] | None = None,
	filters: list[dict] | None = None,
	group_by: list[str] | None = None,
	aggregates: list[dict] | None = None,
	sort: list[dict] | None = None,
	limit: int = 50,
	header_row: int | None = None,
	runtime: ToolRuntime = None,
) -> dict:
	"""Analyze every row of one sheet exactly; use it for totals, counts, averages and lookups instead of
	reading the table text. Columns are header names or letters (A, B, ...).
	filters: [{"column", "op", "value"}]; op is =, !=, >, >=, <, <=, contains, not contains, starts with,
	in, not in (value is a list), is empty, is not empty. Numbers like "1,234", "$5" and "10%" compare as
	numbers; dates compare with YYYY-MM-DD.
	group_by: column names. aggregates: [{"fn": count|count_distinct|sum|avg|min|max|median, "column",
	"as"}]; count without a column counts rows. sort: [{"column", "desc": true}]. limit: rows returned
	(max 500). sheet: the sheet name (default the first). header_row: 1-based (default the first row with
	data)."""
	spec = {
		"columns": columns,
		"filters": filters,
		"group_by": group_by,
		"aggregates": aggregates,
		"sort": sort,
		"limit": limit,
	}
	args = {"file": file, "sheet": sheet, "header_row": header_row, **spec}
	return base.execute(
		"query_spreadsheet",
		lambda: _query(file, sheet, header_row, spec, runtime),
		doctype="File",
		args=args,
		runtime=runtime,
	)


@tool
def write_spreadsheet(
	file_name: str,
	sheets_data: list[dict] | None = None,
	source: str | None = None,
	edits: list[dict] | None = None,
	append: list[dict] | None = None,
	runtime: ToolRuntime = None,
) -> dict:
	"""Make a new .xlsx or .csv file in this chat, for the user to download or attach to a record with
	attach_file. The user confirms first. The source file is never changed.
	file_name: ends with .xlsx or .csv. source: a chat attachment id or File name to copy and change.
	sheets_data: new sheets [{"name", "columns": [...], "rows": [[...], ...]}]; a sheet with the name of a
	source sheet replaces it. edits: [{"sheet", "cell": "B2", "value"}]. append: [{"sheet", "rows"}].
	A value is text, a number, true/false or null; a formula is {"formula": "=SUM(B2:B9)"} (.xlsx only,
	common functions only). Give the download_url to the user."""
	args = {
		"file_name": file_name,
		"sheets_data": sheets_data,
		"source": source,
		"edits": edits,
		"append": append,
	}
	return base.execute(
		"write_spreadsheet",
		lambda: _write(args, runtime),
		operation="create",
		doctype="File",
		args=args,
		runtime=runtime,
		savepoint=True,
	)


def precheck(args: dict):
	"""See ai_assistant.tools.preview.precheck."""
	guard.check("File", "create")
	build(args)


def preview_rows(args: dict) -> tuple[list[str], list[tuple]]:
	name, _data, summary = build(args)
	rows = [(name, s["sheet"], s["rows"], ", ".join(map(str, s["sample"]))[:300]) for s in summary["sheets"]]
	rows += [(name, e.get("sheet") or "", e.get("cell"), e.get("value")) for e in args.get("edits") or []]
	return ["File", "Sheet", "Rows or cell", "First row or value"], rows


def build(args: dict, runtime=None) -> tuple[str, bytes, dict]:
	"""(file name, bytes, summary) of the file write_spreadsheet makes. Raises on any bad argument."""
	name = _file_name(args.get("file_name"))
	new = [_new_sheet(s) for s in _list(args.get("sheets_data"), "sheets_data")]
	edits, append = _list(args.get("edits"), "edits"), _list(args.get("append"), "append")
	if not (new or edits or append or args.get("source")):
		frappe.throw(_("Give sheets_data, a source, edits or rows to append."))
	if sum(len(r) for s in new for r in s.rows) > MAX_WRITE_CELLS:
		frappe.throw(_("The file would have too many cells."))
	if args.get("source"):
		book = sheets.load_for_edit(*files.file_content(args["source"], runtime))
	else:
		from openpyxl import Workbook

		book = Workbook()
		book.remove(book.active)
	_apply(book, new, edits, append)
	if not book.worksheets:
		frappe.throw(_("The file has no sheets."))
	tables = [
		sheets.Sheet(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in book.worksheets
	]
	data = sheets.write(name, tables) if sheets.extension(name) == "csv" else sheets.save(book)
	summary = {
		"sheets": [{"sheet": t.name, "rows": len(t.rows), "sample": (t.rows or [[]])[0][:10]} for t in tables]
	}
	return name, data, summary


def _inspect(file: str, runtime) -> dict:
	name, data = files.file_content(file, runtime)
	out = []
	for sheet in sheets.read(name, data):
		columns, rows = sheet_query.table(sheet)
		out.append(
			{
				"sheet": sheet.name,
				"rows": len(rows),
				"columns": columns,
				"profile": sheet_query.profile(columns, rows),
				"first_rows": [[sheets.plain(v) for v in r] for r in rows[:SAMPLE_ROWS]],
				"truncated": sheet.truncated,
			}
		)
	return {"file": name, "sheets": out, "note": _("Formula cells show the values Excel last saved.")}


def _query(file: str, sheet: str | None, header_row: int | None, spec: dict, runtime) -> dict:
	name, data = files.file_content(file, runtime)
	found = _sheet(sheets.read(name, data), sheet)
	columns, rows = sheet_query.table(found, header_row)
	return {
		"file": name,
		"sheet": found.name,
		"truncated_file": found.truncated,
		**sheet_query.run(columns, rows, spec),
	}


def _write(args: dict, runtime) -> dict:
	guard.check("File", "create")
	ctx = turn.of(runtime)
	if not ctx.conversation:
		frappe.throw(_("A file can be made only in a conversation."))
	conv = conversations.load_own(ctx.conversation)
	name, data, summary = build(args, runtime)
	att, file = attachments.create_generated(conv, name, data)
	return {
		"file": att.file_name,
		"attachment": att.name,
		"download_url": file.file_url,
		"result": "created",
		**summary,
	}


def _apply(book, new: list, edits: list, append: list):
	for sheet in new:
		if sheet.name in book.sheetnames:
			book.remove(book[sheet.name])
		sheets.put_rows(book.create_sheet(sheet.name), sheet.rows)
	for edit in edits:
		cell = str(edit.get("cell") or "").upper()
		if not CELL.match(cell):
			frappe.throw(_("Cell {0} is not an address such as B2.").format(cell or "?"))
		sheets.put(_worksheet(book, edit.get("sheet"))[cell], edit.get("value"))
	for item in append:
		ws = _worksheet(book, item.get("sheet"))
		empty = ws.max_row == 1 and all(c.value is None for c in ws[1])
		sheets.put_rows(ws, _rows(item.get("rows")), start_row=1 if empty else ws.max_row + 1)


def _worksheet(book, name):
	if not book.worksheets:
		frappe.throw(_("The file has no sheets."))
	if not name:
		return book.worksheets[0]
	if name not in book.sheetnames:
		frappe.throw(_("Sheet {0} does not exist. Sheets: {1}").format(name, ", ".join(book.sheetnames)))
	return book[name]


def _sheet(found: list, name: str | None):
	if not found:
		frappe.throw(_("The file has no sheets."))
	if not name:
		return found[0]
	match = next((s for s in found if s.name.lower() == str(name).strip().lower()), None)
	if not match:
		frappe.throw(
			_("Sheet {0} does not exist. Sheets: {1}").format(name, ", ".join(s.name for s in found))
		)
	return match


def _new_sheet(item) -> sheets.Sheet:
	if not isinstance(item, dict):
		frappe.throw(_("Each sheet is an object with name, columns and rows."))
	columns = item.get("columns") or []
	if not isinstance(columns, list):
		frappe.throw(_("columns must be a list."))
	rows = _rows(item.get("rows"))
	return sheets.Sheet(sheets.title(item.get("name")), ([list(columns)] if columns else []) + rows)


def _rows(rows) -> list[list]:
	if rows is None:
		return []
	if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
		frappe.throw(_("rows must be a list of lists."))
	for row in rows:
		for value in row:
			if not (value is None or isinstance(value, str | int | float | bool) or _is_formula(value)):
				frappe.throw(_("A cell value must be text, a number, true/false, null or a formula."))
	return rows


def _is_formula(value) -> bool:
	return isinstance(value, dict) and set(value) == {"formula"}


def _list(value, name: str) -> list:
	if value is None:
		return []
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(name))
	return value


def _file_name(value) -> str:
	name = os.path.basename(str(value or "")).strip()
	if sheets.extension(name) not in sheets.WRITE_TYPES:
		frappe.throw(_("The file name must end with .xlsx or .csv."))
	return name
