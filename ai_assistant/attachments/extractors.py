"""Text extraction per kind (SPEC §6.8). Office files are parsed, never opened with macros."""

import csv
import io
import zipfile
from dataclasses import dataclass

import frappe
from frappe import _

MAX_UNZIPPED = 100 * 1024 * 1024
MAX_SHEET_ROWS = 2000


@dataclass
class Extracted:
	text: str
	page_count: int | None = None


def extract(kind: str, data: bytes, file_name: str = "") -> Extracted:
	if kind == "pdf":
		return _pdf(data)
	if kind == "document":
		return Extracted(_docx(data))
	if kind == "spreadsheet":
		return Extracted(_csv(data) if file_name.lower().endswith(".csv") else _xlsx(data))
	if kind == "text":
		return Extracted(decode_text(data))
	frappe.throw(_("No text extractor for {0} files.").format(kind))


def decode_text(data: bytes) -> str:
	try:
		return data.decode("utf-8-sig")
	except UnicodeDecodeError:
		frappe.throw(_("The file is not valid UTF-8 text."))


def check_zip(data: bytes):
	"""Zip-based Office files: refuse when the unpacked size exceeds 100 MB (zip bomb)."""
	try:
		with zipfile.ZipFile(io.BytesIO(data)) as archive:
			if sum(info.file_size for info in archive.infolist()) > MAX_UNZIPPED:
				frappe.throw(_("The file is too large when unpacked."))
	except zipfile.BadZipFile:
		frappe.throw(_("The file is damaged or not an Office file."))


def _pdf(data: bytes) -> Extracted:
	from pypdf import PdfReader

	reader = PdfReader(io.BytesIO(data))
	pages = [(page.extract_text() or "").strip() for page in reader.pages]
	text = "\n\n".join(f"[Page {i}]\n{t}" for i, t in enumerate(pages, 1) if t)
	return Extracted(text, len(reader.pages))


def _docx(data: bytes) -> str:
	import docx

	check_zip(data)
	document = docx.Document(io.BytesIO(data))
	parts = [p.text for p in document.paragraphs if p.text.strip()]
	for table in document.tables:
		rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
		parts.append(markdown_table(rows))
	return "\n\n".join(parts)


def _xlsx(data: bytes) -> str:
	from openpyxl import load_workbook

	check_zip(data)
	workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
	parts = []
	for sheet in workbook.worksheets:
		rows = []
		for i, row in enumerate(sheet.iter_rows(values_only=True)):
			if i >= MAX_SHEET_ROWS:
				rows.append(["…"])
				break
			if any(v not in (None, "") for v in row):
				rows.append(["" if v is None else str(v) for v in row])
		if rows:
			parts.append(f"## Sheet: {sheet.title}\n{markdown_table(rows)}")
	workbook.close()
	return "\n\n".join(parts)


def _csv(data: bytes) -> str:
	text = decode_text(data)
	try:
		dialect = csv.Sniffer().sniff(text[:4096])
	except csv.Error:
		dialect = csv.excel
	rows = list(csv.reader(io.StringIO(text), dialect))[: MAX_SHEET_ROWS + 1]
	return markdown_table(rows)


def markdown_table(rows: list[list[str]]) -> str:
	if not rows:
		return ""
	width = max(len(r) for r in rows)
	rows = [
		[str(c).replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (width - len(r)) for r in rows
	]
	lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
	lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
	return "\n".join(lines)
