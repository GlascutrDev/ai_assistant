import socket
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.rag import loaders, web

PUBLIC = "93.184.216.34"


def resolve(mapping: dict):
	def fake(host, port, proto=0):
		return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (mapping.get(host, PUBLIC), port))]

	return patch("socket.getaddrinfo", side_effect=fake)


class FakeResponse:
	def __init__(self, status=200, body=b"", kind="text/html", location=None):
		self.status_code, self.body = status, body
		self.headers = {"Content-Type": kind, **({"Location": location} if location else {})}
		self.is_redirect = status in (301, 302, 303, 307, 308)
		self.encoding = "utf-8"

	def iter_content(self, size):
		for i in range(0, len(self.body), size):
			yield self.body[i : i + size]

	def close(self):
		pass


PAGE = b"<html><head><title>Returns</title><script>x()</script></head><body><nav>Menu</nav><main><h1>Policy</h1><p>30 days.</p></main></body></html>"


class TestWebKnowledge(IntegrationTestCase):
	def test_only_public_https_addresses(self):
		for url in (
			"http://example.com",
			"https://user:pw@example.com",
			"https://example.com:8443/x",
			"ftp://x",
		):
			with self.subTest(url=url), self.assertRaises(web.UnsafeURLError):
				web.check_url(url)
		for address in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.35", "::1", "fd00::1"):
			with (
				self.subTest(address=address),
				resolve({"inside.test": address}),
				self.assertRaises(web.UnsafeURLError),
			):
				web.check_url("https://inside.test/page")
		with resolve({}):
			web.check_url("https://example.com/page")

	def test_redirect_to_an_internal_host_is_refused(self):
		responses = [FakeResponse(302, location="https://metadata.test/latest")]
		with (
			resolve({"metadata.test": "169.254.169.254"}),
			patch("requests.get", side_effect=responses),
			self.assertRaises(web.UnsafeURLError),
		):
			web.fetch("https://example.com/start")

	def test_html_becomes_main_text_and_limits_apply(self):
		with resolve({}), patch("requests.get", return_value=FakeResponse(body=PAGE)):
			text = web.fetch("https://example.com/returns")
		self.assertEqual(text, "Returns\nPolicy\n30 days.")
		big = FakeResponse(body=b"a" * (web.MAX_BYTES + 1), kind="text/plain")
		with (
			resolve({}),
			patch("requests.get", return_value=big),
			self.assertRaisesRegex(frappe.ValidationError, "larger"),
		):
			web.fetch("https://example.com/big")
		with (
			resolve({}),
			patch("requests.get", return_value=FakeResponse(kind="image/png")),
			self.assertRaises(frappe.ValidationError),
		):
			web.fetch("https://example.com/logo")

	def test_saving_a_page_fetches_it_and_indexes_on_change(self):
		with (
			resolve({}),
			patch("requests.get", return_value=FakeResponse(body=PAGE)),
			patch("ai_assistant.rag.indexer.sync") as synced,
		):
			doc = frappe.get_doc(
				{
					"doctype": "AI Knowledge Document",
					"title": "Returns",
					"enabled": 1,
					"source_url": "https://example.com/r",
				}
			).insert()
			doc.reload()
			self.assertIn("30 days.", doc.url_text)
			self.assertIn("Source: https://example.com/r", loaders.knowledge_text(doc))
			self.assertFalse(web.refresh(doc.name))
		self.assertEqual(synced.call_count, 1)

	def test_fetch_error_is_kept_on_the_document(self):
		with resolve({}), patch("requests.get", return_value=FakeResponse(status=404)):
			doc = frappe.get_doc(
				{
					"doctype": "AI Knowledge Document",
					"title": "Gone",
					"enabled": 1,
					"source_url": "https://example.com/gone",
				}
			).insert()
		self.assertIn("404", frappe.db.get_value("AI Knowledge Document", doc.name, "url_error"))

	def test_internal_address_cannot_be_saved(self):
		with resolve({"intranet.test": "10.1.2.3"}), self.assertRaises(web.UnsafeURLError):
			frappe.get_doc(
				{
					"doctype": "AI Knowledge Document",
					"title": "Inside",
					"source_url": "https://intranet.test/",
				}
			).insert()
