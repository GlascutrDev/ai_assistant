"""Web pages as knowledge (SPEC §8.1.1): fetch an admin-given https page as text, refusing internal hosts."""

import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import frappe
from frappe import _
from frappe.utils import now_datetime

DOCTYPE = "AI Knowledge Document"
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = (5, 15)
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "text/markdown")
DROP_TAGS = ("script", "style", "noscript", "template", "svg", "nav", "footer", "header", "form", "iframe")


class UnsafeURLError(frappe.ValidationError):
	pass


def check_url(url: str):
	"""Raise unless `url` is https on a public host (every address it resolves to is global)."""
	parts = urlparse((url or "").strip())
	if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
		frappe.throw(_("Use an https address without a user name or password."), UnsafeURLError)
	if parts.port not in (None, 443):
		frappe.throw(_("Use the standard https port."), UnsafeURLError)
	try:
		infos = socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP)
	except socket.gaierror:
		frappe.throw(_("The host {0} cannot be found.").format(parts.hostname), UnsafeURLError)
	for info in infos:
		address = ipaddress.ip_address(info[4][0].split("%")[0])
		if not address.is_global or address.is_multicast:
			frappe.throw(_("Private or internal addresses are not allowed."), UnsafeURLError)


def fetch(url: str) -> str:
	"""The page text. Each redirect target is checked again; bodies over MAX_BYTES are refused."""
	import requests

	for _hop in range(MAX_REDIRECTS + 1):
		check_url(url)
		response = requests.get(
			url,
			timeout=TIMEOUT,
			allow_redirects=False,
			stream=True,
			headers={
				"User-Agent": "Frappe-AI-Assistant/1 (knowledge indexer)",
				"Accept": ", ".join(TEXT_TYPES),
			},
		)
		if response.is_redirect:
			url = urljoin(url, response.headers.get("Location", ""))
			response.close()
			continue
		if response.status_code != 200:
			frappe.throw(_("The page answered with status {0}.").format(response.status_code))
		return _text(response)
	frappe.throw(_("The page redirects too many times."))


def refresh(name: str) -> bool:
	"""Background job: fetch the page of one knowledge document and re-index it when its text changed."""
	from ai_assistant.rag import indexer

	doc = frappe.get_doc(DOCTYPE, name)
	if not doc.source_url:
		return False
	try:
		text = fetch(doc.source_url)
	except Exception as e:
		frappe.clear_messages()
		if not isinstance(e, frappe.ValidationError):
			frappe.log_error(f"AI Assistant could not fetch {doc.source_url}")
		doc.db_set({"url_error": str(e)[:500] or _("The page could not be read.")}, update_modified=False)
		return False
	changed = _digest(text) != _digest(doc.url_text or "")
	doc.db_set({"url_text": text, "url_fetched_on": now_datetime(), "url_error": None}, update_modified=False)
	if changed and doc.enabled:
		indexer.sync(DOCTYPE, name)
	return changed


def refresh_all():
	"""Daily: fetch every enabled web page again."""
	for name in frappe.get_all(DOCTYPE, filters={"enabled": 1, "source_url": ["is", "set"]}, pluck="name"):
		refresh(name)


def enqueue_refresh(doc, method=None):
	"""AIKnowledgeDocument.on_update: fetch soon after the address is set or changed."""
	if doc.source_url and (doc.has_value_changed("source_url") or not doc.url_fetched_on):
		frappe.enqueue(
			"ai_assistant.rag.web.refresh",
			queue="short",
			enqueue_after_commit=True,
			now=bool(frappe.in_test),
			name=doc.name,
		)


def _text(response) -> str:
	kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
	if kind not in TEXT_TYPES:
		frappe.throw(_("Pages of type {0} cannot be indexed.").format(kind or "?"))
	body = b""
	for chunk in response.iter_content(64 * 1024):
		body += chunk
		if len(body) > MAX_BYTES:
			response.close()
			frappe.throw(_("The page is larger than {0} MB.").format(MAX_BYTES // (1024 * 1024)))
	text = body.decode(response.encoding or "utf-8", errors="replace")
	return _html_text(text) if "html" in kind else text.strip()


def _html_text(html: str) -> str:
	from bs4 import BeautifulSoup

	soup = BeautifulSoup(html, "html.parser")
	for tag in soup(DROP_TAGS):
		tag.decompose()
	title = soup.title.get_text(" ", strip=True) if soup.title else ""
	main = soup.find("main") or soup.find("article") or soup.body or soup
	lines = [line.strip() for line in main.get_text("\n").splitlines()]
	return "\n".join(filter(None, [title, *lines]))


def _digest(text: str) -> str:
	return hashlib.sha256(text.encode()).hexdigest()
