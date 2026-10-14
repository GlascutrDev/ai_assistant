"""Keep `ai_embedding` in step with the knowledge sources (SPEC §8.2, §8.4)."""

import frappe
from frappe import _
from frappe.utils import now_datetime
from langchain_core.messages.utils import count_tokens_approximately
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ai_assistant.llm import registry, usage
from ai_assistant.persistence import schema
from ai_assistant.rag import loaders
from ai_assistant.rag.store import FrappeVectorStore
from ai_assistant.services import settings

SOURCES_KEY = "ai_assistant:rag_sources"


def on_doc_change(doc, method=None):
	if doc.doctype in enabled_sources():
		_enqueue("ai_assistant.rag.indexer.sync", doctype=doc.doctype, name=doc.name)


def on_doc_trash(doc, method=None):
	if doc.doctype in enabled_sources():
		FrappeVectorStore(None).delete_source(doc.doctype, doc.name)


def on_doc_rename(doc, method=None, old=None, new=None, merge=False):
	if doc.doctype in enabled_sources():
		FrappeVectorStore(None).delete_source(doc.doctype, old)
		_enqueue("ai_assistant.rag.indexer.sync", doctype=doc.doctype, name=new)


def enabled_sources() -> set[str]:
	sources = frappe.cache.get_value(SOURCES_KEY)
	if sources is None:
		conf = settings.get()
		sources = []
		if conf.rag_enabled:
			sources = [row.source_doctype for row in conf.knowledge_sources if row.enabled]
			sources.append(loaders.KNOWLEDGE_DOCTYPE)
		frappe.cache.set_value(SOURCES_KEY, sources)
	return set(sources)


def clear_source_cache():
	frappe.cache.delete_value(SOURCES_KEY)


def sync(doctype: str, name: str):
	"""Replace the chunks of one source document. Runs as a background job."""
	conf = settings.get()
	if not conf.rag_enabled or conf.index_stale or not _table_ready():
		return
	store = FrappeVectorStore(registry.get_embeddings())
	store.delete_source(doctype, name)
	if not frappe.db.exists(doctype, name):
		return
	doc = frappe.get_doc(doctype, name)
	source = _source_row(doctype)
	if not _indexable(doc, source):
		return
	chunks = _splitter().split_text(loaders.text_of(doc, source.content_fields if source else None))
	meta = {
		"source_doctype": doctype,
		"source_name": name,
		"title": loaders.title_of(doc),
		"modified": str(doc.modified),
	}
	if doctype == loaders.KNOWLEDGE_DOCTYPE:
		meta["visible_to_roles"] = [row.role for row in doc.visible_to_roles]
	store.add_texts(chunks, [{**meta, "chunk_no": i} for i, _ in enumerate(chunks)])
	_log_usage(chunks)
	if doctype == loaders.KNOWLEDGE_DOCTYPE:
		frappe.db.set_value(doctype, name, "last_indexed", now_datetime(), update_modified=False)


def rebuild_all():
	"""Recreate the table with the embedding profile's dimensions and index every source."""
	dim = schema.embedding_dimensions()
	if not dim:
		frappe.throw(_("Set an embedding model with dimensions first."))
	schema.create_embedding_table(dim, drop=True)
	frappe.db.set_single_value(settings.SETTINGS, "index_stale", 0)
	clear_source_cache()
	for row in settings.get().knowledge_sources:
		if row.enabled:
			for name in frappe.get_all(row.source_doctype, pluck="name"):
				sync(row.source_doctype, name)
	for name in frappe.get_all(loaders.KNOWLEDGE_DOCTYPE, filters={"enabled": 1}, pluck="name"):
		sync(loaders.KNOWLEDGE_DOCTYPE, name)
	frappe.db.commit()


def reindex_changed_sources():
	"""Daily: re-sync source documents changed in the last day, in case a job was lost."""
	for doctype in enabled_sources():
		for name in frappe.get_all(
			doctype, filters={"modified": [">", frappe.utils.add_days(None, -1)]}, pluck="name"
		):
			sync(doctype, name)


def is_searchable() -> bool:
	conf = settings.get()
	return bool(conf.rag_enabled and not conf.index_stale and _table_ready())


def _indexable(doc, source) -> bool:
	if doc.doctype == loaders.KNOWLEDGE_DOCTYPE:
		return bool(doc.enabled)
	return bool(source) and loaders.matches_filters(doc.doctype, doc.name, source.filters_json)


def _source_row(doctype: str):
	return next(
		(r for r in settings.get().knowledge_sources if r.source_doctype == doctype and r.enabled), None
	)


def _table_ready() -> bool:
	dim = schema.embedding_dimensions()
	return bool(dim) and schema.embedding_table_dimensions() == dim


def _splitter():
	conf = settings.get()
	return RecursiveCharacterTextSplitter(
		chunk_size=conf.chunk_size or 1200, chunk_overlap=conf.chunk_overlap or 150
	)


def _log_usage(chunks: list[str]):
	if chunks:
		usage.record(
			profile_id=settings.get().embedding_model,
			purpose="embedding",
			input_tokens=count_tokens_approximately(chunks),
		)


def _enqueue(method: str, **kwargs):
	frappe.enqueue(method, queue="short", enqueue_after_commit=True, now=bool(frappe.in_test), **kwargs)
