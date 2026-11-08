"""Text extraction per kind (SPEC §6.8). Office files are parsed, never opened with macros."""

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
		return Extracted(_spreadsheet(data, file_name))
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


def _spreadsheet(data: bytes, file_name: str) -> str:
	"""Each sheet as a markdown table of at most MAX_SHEET_ROWS rows. The spreadsheet tools see every row."""
	from ai_assistant.attachments import sheets

	parts = []
	for sheet in sheets.read(file_name, data):
		rows = [r for r in sheet.rows if any(v is not None for v in r)]
		more = len(rows) > MAX_SHEET_ROWS + 1 or sheet.truncated
		cells = [["" if v is None else str(sheets.plain(v)) for v in r] for r in rows[: MAX_SHEET_ROWS + 1]]
		if more:
			cells.append(["…"])
		if cells:
			parts.append(f"## Sheet: {sheet.name}\n{markdown_table(cells)}")
	return "\n\n".join(parts)


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
