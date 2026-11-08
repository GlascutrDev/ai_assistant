import io
import os

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant import tools
from ai_assistant.api import chat
from ai_assistant.attachments import extractors, sheet_query, sheets, upload
from ai_assistant.services import actions, conversations, settings
from ai_assistant.services import attachments as files
from ai_assistant.tests import factories, fake_llm
from ai_assistant.tests.test_attachments import xlsx_bytes
from ai_assistant.tools import preview, spreadsheets

XLS = os.path.join(os.path.dirname(__file__), "fixtures", "tiny.xls")
TYPES = settings.DEFAULT_FILE_TYPES.replace(" ", "\n")
SALES = [
	["Region", "Item", "Qty", "Amount", "Date"],
	["East", "Tea", 2, "1,200.50", "2026-01-05"],
	["West", "Tea", 5, "$300", "2026-02-10"],
	["East", "Coffee", 1, 99, "2026-02-11"],
	["North", "Cake", None, "", "2026-03-01"],
]


def csv_bytes(rows=SALES, delimiter=",") -> bytes:
	return "\n".join(
		delimiter.join("" if v is None else str(v).replace(",", "") for v in r) for r in rows
	).encode()


def query(rows=SALES, **spec) -> dict:
	columns, data = sheet_query.table(sheets.Sheet("S", [list(r) for r in rows]))
	return sheet_query.run(columns, data, spec)


class TestSheetReading(IntegrationTestCase):
	def setUp(self):
		factories.configure(attachments_enabled=1, allowed_file_types=TYPES)

	def test_every_type_reads_as_rows(self):
		self.assertEqual(sheets.read("a.xlsx", xlsx_bytes(SALES))[0].rows[1][:3], ["East", "Tea", 2])
		self.assertEqual(sheets.read("a.csv", csv_bytes())[0].rows[2][0], "West")
		self.assertEqual(sheets.read("a.tsv", csv_bytes(delimiter="\t"))[0].rows[0][4], "Date")
		with open(XLS, "rb") as f:
			xls = f.read()
		self.assertEqual(
			sheets.read("tiny.xls", xls)[0].rows,
			[["Item", "Qty", "Price"], ["Tea", 2.0, 3.5], ["Coffee", 5.0, 4.0]],
		)
		self.assertIn("| Coffee | 5 | 4 |", extractors.extract("spreadsheet", xls, "tiny.xls").text)

	def test_xls_upload_is_sniffed(self):
		with open(XLS, "rb") as f:
			self.assertEqual(upload.check("tiny.xls", f.read()).kind, "spreadsheet")
		with self.assertRaises(upload.UploadRefusedError):
			upload.check("renamed.xls", xlsx_bytes(SALES))


class TestSheetQuery(IntegrationTestCase):
	def test_filters_compare_numbers_text_and_dates(self):
		self.assertEqual(query(filters=[{"column": "Amount", "op": ">", "value": 250}])["matched_rows"], 2)
		self.assertEqual(
			query(filters=[{"column": "item", "op": "contains", "value": "TE"}])["matched_rows"], 2
		)
		self.assertEqual(
			query(filters=[{"column": "Item", "op": "not contains", "value": "e"}])["matched_rows"], 0
		)
		self.assertEqual(query(filters=[{"column": "B", "op": "=", "value": "tea"}])["matched_rows"], 2)
		self.assertEqual(query(filters=[{"column": "Qty", "op": "is empty"}])["rows"][0]["Region"], "North")
		in_feb = query(filters=[{"column": "Date", "op": "starts with", "value": "2026-02"}])
		self.assertEqual(in_feb["matched_rows"], 2)

	def test_group_aggregate_and_sort(self):
		result = query(
			group_by=["Region"],
			aggregates=[{"fn": "sum", "column": "Amount", "as": "total"}, {"fn": "count"}],
			sort=[{"column": "total", "desc": True}],
		)
		self.assertEqual(result["columns"], ["Region", "total", "count"])
		self.assertEqual(result["rows"][0], {"Region": "East", "total": 1299.5, "count": 2})
		self.assertIsNone(next(r for r in result["rows"] if r["Region"] == "North")["total"])
		self.assertEqual(query(aggregates=[{"fn": "avg", "column": "Qty"}])["rows"][0]["avg(Qty)"], 2.666667)

	def test_bad_column_or_operator_is_explained(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Columns: Region"):
			query(filters=[{"column": "Price", "op": "=", "value": 1}])
		with self.assertRaises(frappe.ValidationError):
			query(filters=[{"column": "Qty", "op": "~", "value": 1}])

	def test_profile_types(self):
		columns, data = sheet_query.table(sheets.Sheet("S", [list(r) for r in SALES]))
		by_name = {p["column"]: p for p in sheet_query.profile(columns, data)}
		self.assertEqual((by_name["Qty"]["type"], by_name["Qty"]["sum"]), ("number", 8))
		self.assertEqual(by_name["Region"]["distinct"], 3)


class TestSheetWriting(IntegrationTestCase):
	def test_text_stays_text_and_formulas_are_checked(self):
		data = sheets.write("out.xlsx", [sheets.Sheet("S", [["=1+1", {"formula": "=SUM(A2:A3)"}]])])
		from openpyxl import load_workbook

		ws = load_workbook(io.BytesIO(data)).active
		self.assertEqual((ws["A1"].data_type, ws["B1"].data_type), ("s", "f"))
		for bad in ("=WEBSERVICE(A1)", "=HYPERLINK(A1)", "=SUM([book.xlsx]S!A1)", "=cmd|' /C calc'!A0"):
			with self.assertRaises(frappe.ValidationError):
				sheets.check_formula(bad)

	def test_csv_escapes_formula_text(self):
		data = sheets.write("out.csv", [sheets.Sheet("S", [["=HYPERLINK(1)", "@x", "-5", "-x", 3]])])
		self.assertEqual(data.decode("utf-8-sig").strip(), "'=HYPERLINK(1),'@x,-5,'-x,3")


class TestWriteSpreadsheetTool(IntegrationTestCase):
	def setUp(self):
		factories.configure(attachments_enabled=1, allowed_file_types=TYPES)
		self.user = factories.assistant_user()

	def upload(self, name: str, data: bytes):
		with self.set_user(self.user):
			conv = conversations.get_or_create(None)
			att = files.create(conv, name, data)
			files.process(att.name)
		return frappe.get_doc("AI Attachment", att.name)

	def test_inspect_and_query_a_chat_attachment(self):
		att = self.upload("sales.xlsx", xlsx_bytes(SALES))
		runtime = fake_llm.FakeRuntime(self.user, att.conversation)
		with self.set_user(self.user):
			found = spreadsheets.inspect_spreadsheet.func(file=att.name, runtime=runtime)
			total = spreadsheets.query_spreadsheet.func(
				file=att.name, aggregates=[{"fn": "sum", "column": "Qty"}], runtime=runtime
			)
		self.assertEqual(found["sheets"][0]["rows"], 4)
		self.assertEqual(total["rows"], [{"sum(Qty)": 8}])

	def test_other_users_file_is_refused(self):
		att = self.upload("sales.csv", csv_bytes())
		with self.set_user(factories.assistant_user()):
			result = spreadsheets.inspect_spreadsheet.invoke({"file": att.name})
		self.assertEqual(result["outcome"], "permission_denied")

	def test_write_pauses_then_saves_a_private_chat_file(self):
		source = self.upload("sales.xlsx", xlsx_bytes(SALES))
		args = {
			"file_name": "summary.xlsx",
			"source": source.name,
			"edits": [{"cell": "F1", "value": "Checked"}],
			"sheets_data": [
				{"name": "Totals", "columns": ["Total"], "rows": [[{"formula": "=SUM(Sheet!C2:C5)"}]]}
			],
		}
		model = fake_llm.fake_chat(fake_llm.tool_call("write_spreadsheet", args), "Title", "Here it is.")
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			chat.send_message(text="add totals", conversation=source.conversation)
			request = actions.pending_for(source.conversation)[0]
			self.assertEqual((request.operation, request.target_doctype), ("create", "File"))
			self.assertIn("Totals", request.diff_html)
			self.assertFalse(frappe.db.exists("AI Attachment", {"file_name": "summary.xlsx"}))
			chat.decide_action(action_request=request.name, decision="approve")
		made = frappe.get_doc("AI Attachment", {"file_name": "summary.xlsx"})
		self.assertEqual((made.status, made.sent, made.conversation), ("Ready", 1, source.conversation))
		self.assertTrue(frappe.db.get_value("File", made.file, "is_private"))
		book = sheets.read("summary.xlsx", files.read_bytes(made))
		self.assertEqual([s.name for s in book], ["Sheet", "Totals"])
		self.assertEqual(book[0].rows[0][5], "Checked")
		self.assertEqual(len(sheets.read("sales.xlsx", files.read_bytes(source))[0].rows[0]), 5)

	def test_bad_request_fails_on_the_card(self):
		with self.set_user(self.user):
			error = preview.precheck("write_spreadsheet", {"file_name": "x.exe", "sheets_data": []})
		self.assertIn(".xlsx or .csv", error)

	def test_offered_only_with_attachments_and_writes(self):
		self.assertIn("write_spreadsheet", tools.write_tool_names())
		self.assertNotIn("write_spreadsheet", [t.name for t in tools.for_turn(read_only=True)])
		self.assertNotIn("write_spreadsheet", [t.name for t in tools.for_turn(files=False)])
		self.assertIn("query_spreadsheet", [t.name for t in tools.for_turn(read_only=True)])
