"""Spreadsheet files as tables: read .xlsx/.xlsm/.xls/.csv/.tsv, write .xlsx/.csv (SPEC §6.8.1).

Files are parsed only. Macros never run, and formulas are read as the values Excel last saved."""

import csv
import datetime
import io
import re
from dataclasses import dataclass, field

import frappe
from frappe import _

from ai_assistant.attachments.extractors import check_zip, decode_text

READ_TYPES = ("xlsx", "xlsm", "xls", "csv", "tsv")
WRITE_TYPES = ("xlsx", "csv")
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_SHEETS = 50
# Text that a spreadsheet app would run as a formula (OWASP "CSV injection").
FORMULA_START = ("=", "+", "@", "\t", "\r")
SAFE_FUNCTIONS = frozenset(
	"SUM SUMIF SUMIFS AVERAGE AVERAGEIF AVERAGEIFS MIN MAX COUNT COUNTA COUNTBLANK COUNTIF COUNTIFS ROUND "
	"ROUNDUP ROUNDDOWN ABS IF IFS IFERROR AND OR NOT VLOOKUP HLOOKUP XLOOKUP INDEX MATCH LEN UPPER LOWER "
	"TRIM LEFT RIGHT MID CONCAT CONCATENATE TEXT VALUE DATE YEAR MONTH DAY EOMONTH NETWORKDAYS MEDIAN "
	"PRODUCT SUMPRODUCT".split()
)


@dataclass
class Sheet:
	name: str
	rows: list[list] = field(default_factory=list)
	truncated: bool = False


def extension(file_name: str) -> str:
	return (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""


def read(file_name: str, data: bytes) -> list[Sheet]:
	"""Every sheet with its rows (lists of cell values), at most MAX_ROWS by MAX_COLUMNS each."""
	ext = extension(file_name)
	if ext in ("csv", "tsv"):
		return [_delimited(file_name, data, "\t" if ext == "tsv" else None)]
	if ext in ("xlsx", "xlsm"):
		return _openpyxl(data)
	if ext == "xls":
		return _xlrd(data)
	frappe.throw(_("Files of type .{0} are not spreadsheets.").format(ext or "?"))


def write(file_name: str, sheets: list[Sheet]) -> bytes:
	"""A new .xlsx (one tab per sheet) or .csv (one sheet). Text is always stored as text."""
	ext = extension(file_name)
	if ext == "csv":
		if len(sheets) != 1:
			frappe.throw(_("A .csv file holds one sheet. Use .xlsx for more."))
		out = io.StringIO()
		csv.writer(out).writerows([[_csv_cell(v) for v in row] for row in sheets[0].rows])
		return out.getvalue().encode("utf-8-sig")
	if ext != "xlsx":
		frappe.throw(_("Spreadsheets can be written as .xlsx or .csv only."))
	from openpyxl import Workbook

	book = Workbook()
	book.remove(book.active)
	for sheet in sheets:
		put_rows(book.create_sheet(title(sheet.name)), sheet.rows)
	return save(book)


def put_rows(ws, rows: list[list], start_row: int = 1):
	for r, row in enumerate(rows, start=start_row):
		for c, value in enumerate(row, start=1):
			put(ws.cell(row=r, column=c), value)


def put(cell, value):
	"""A literal value, or a formula given as {"formula": "=SUM(B2:B9)"} that uses SAFE_FUNCTIONS only."""
	if isinstance(value, dict) and "formula" in value:
		cell.value = check_formula(value["formula"])
		return
	cell.value = value
	if isinstance(value, str):
		cell.data_type = "s"


def check_formula(text) -> str:
	formula = "=" + str(text or "").strip().lstrip("=")
	names = set(re.findall(r"([A-Za-z][A-Za-z0-9._]*)\s*\(", formula))
	unsafe = {n.upper() for n in names} - SAFE_FUNCTIONS
	if unsafe or re.search(r"[\[\]|]|://|!'?[A-Za-z]:", formula) or len(formula) > 500:
		frappe.throw(_("Formula {0} is not allowed. Use plain functions such as SUM or IF.").format(formula))
	return formula


def save(book) -> bytes:
	out = io.BytesIO()
	book.save(out)
	return out.getvalue()


def load_for_edit(file_name: str, data: bytes):
	"""An openpyxl workbook to change: an .xlsx keeps its formatting; other types are copied as values."""
	from openpyxl import Workbook, load_workbook

	if extension(file_name) == "xlsx":
		check_zip(data)
		return load_workbook(io.BytesIO(data))
	book = Workbook()
	book.remove(book.active)
	for sheet in read(file_name, data):
		put_rows(book.create_sheet(title(sheet.name)), sheet.rows)
	return book


def plain(value):
	"""A cell value as JSON-safe data: dates as ISO text, whole floats as int."""
	if isinstance(value, datetime.datetime | datetime.date | datetime.time):
		return value.isoformat()
	if isinstance(value, float) and value.is_integer():
		return int(value)
	return value


def _openpyxl(data: bytes) -> list[Sheet]:
	from openpyxl import load_workbook

	check_zip(data)
	book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
	try:
		return [_collect(ws.title, ws.iter_rows(values_only=True)) for ws in book.worksheets[:MAX_SHEETS]]
	finally:
		book.close()


def _xlrd(data: bytes) -> list[Sheet]:
	import xlrd

	try:
		book = xlrd.open_workbook(file_contents=data, on_demand=True)
	except xlrd.XLRDError:
		frappe.throw(_("The file is damaged or not an Excel file."))
	sheets = []
	for i in range(min(book.nsheets, MAX_SHEETS)):
		ws = book.sheet_by_index(i)
		rows = ([_xls_value(ws.cell(r, c), book.datemode) for c in range(ws.ncols)] for r in range(ws.nrows))
		sheets.append(_collect(ws.name, rows))
	return sheets


def _xls_value(cell, datemode):
	import xlrd

	if cell.ctype == xlrd.XL_CELL_DATE:
		return xlrd.xldate.xldate_as_datetime(cell.value, datemode)
	if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
		return None
	return cell.value


def _delimited(file_name: str, data: bytes, delimiter: str | None) -> Sheet:
	text = decode_text(data)
	if delimiter:
		dialect = csv.excel_tab
	else:
		try:
			dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
		except csv.Error:
			dialect = csv.excel
	name = file_name.rsplit(".", 1)[0] or "Sheet1"
	return _collect(name, csv.reader(io.StringIO(text), dialect))


def _collect(name: str, rows) -> Sheet:
	sheet = Sheet(name)
	for row in rows:
		if len(sheet.rows) >= MAX_ROWS:
			sheet.truncated = True
			break
		sheet.rows.append([None if v == "" else v for v in list(row)[:MAX_COLUMNS]])
	while sheet.rows and not any(v is not None for v in sheet.rows[-1]):
		sheet.rows.pop()
	return sheet


def _csv_cell(value):
	if isinstance(value, dict):
		frappe.throw(_("Formulas need an .xlsx file."))
	value = plain(value)
	if isinstance(value, str) and (
		value.startswith(FORMULA_START) or (value.startswith("-") and not _is_number(value))
	):
		return "'" + value
	return "" if value is None else value


def _is_number(text: str) -> bool:
	try:
		float(text)
	except ValueError:
		return False
	return True


def title(name) -> str:
	title = re.sub(r"[\[\]:*?/\\]", " ", str(name or "Sheet")).strip()[:31]
	return title or "Sheet"
