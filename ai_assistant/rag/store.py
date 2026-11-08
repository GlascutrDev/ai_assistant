"""Vector store over `ai_embedding` (SPEC §8.3). Search results are permission-filtered per document."""

import json
from collections.abc import Iterable

import frappe
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from ai_assistant.persistence.schema import EMBEDDING_TABLE
from ai_assistant.rag.loaders import KNOWLEDGE_DOCTYPE
from ai_assistant.services import settings

BATCH = 64
OVERFETCH = 4


class FrappeVectorStore(VectorStore):
	def __init__(
		self, embeddings: Embeddings, conversation: str | None = None, sources: list[str] | None = None
	):
		self._embeddings = embeddings
		self.conversation = conversation
		self.sources = sources

	@property
	def embeddings(self) -> Embeddings:
		return self._embeddings

	def add_texts(self, texts: Iterable[str], metadatas: list[dict] | None = None, **kwargs) -> list[str]:
		"""Each metadata needs `source_doctype`, `source_name`, `chunk_no`."""
		texts = list(texts)
		metadatas = metadatas or [{} for _ in texts]
		ids = []
		for start in range(0, len(texts), BATCH):
			batch = texts[start : start + BATCH]
			vectors = self._embeddings.embed_documents(batch)
			for text, meta, vector in zip(batch, metadatas[start : start + BATCH], vectors, strict=True):
				frappe.db.sql(
					f"""insert into `{EMBEDDING_TABLE}`
					(source_doctype, source_name, conversation, chunk_no, content, metadata, embedding)
					values (%s, %s, %s, %s, %s, %s, VEC_FromText(%s))""",
					(
						meta["source_doctype"],
						meta["source_name"],
						self.conversation,
						meta["chunk_no"],
						text,
						json.dumps(meta, default=str),
						json.dumps([float(v) for v in vector]),
					),
				)
				ids.append(str(frappe.db.sql("select last_insert_id()")[0][0]))
		return ids

	@classmethod
	def from_texts(cls, texts, embedding, metadatas=None, **kwargs):
		"""See langchain_core.vectorstores.VectorStore.from_texts."""
		store = cls(embedding, conversation=kwargs.get("conversation"))
		store.add_texts(texts, metadatas)
		return store

	def similarity_search(self, query: str, k: int = 4, **kwargs) -> list[Document]:
		"""Nearest chunks the session user may read. Never returns an unfiltered chunk."""
		return [doc for doc, _ in self.similarity_search_with_score(query, k)]

	def similarity_search_with_score(self, query: str, k: int = 4, **kwargs) -> list[tuple[Document, float]]:
		"""See langchain_core.vectorstores.VectorStore.similarity_search_with_score."""
		results = []
		for row in self._nearest(self._embeddings.embed_query(query), k * OVERFETCH):
			meta = json.loads(row.metadata or "{}")
			if not self._may_read(row, meta):
				continue
			results.append((Document(page_content=row.content, metadata=meta), float(row.distance)))
			if len(results) >= k:
				break
		return results

	def delete_source(self, doctype: str, name: str):
		frappe.db.sql(
			f"delete from `{EMBEDDING_TABLE}` where source_doctype = %s and source_name = %s and conversation is null",
			(doctype, name),
		)

	def _nearest(self, vector: list[float], limit: int) -> list:
		scope = "conversation = %s" if self.conversation else "conversation is null"
		params = [json.dumps([float(v) for v in vector])]
		if self.conversation:
			params.append(self.conversation)
		if self.sources:
			scope += " and source_doctype in ({0})".format(", ".join(["%s"] * len(self.sources)))
			params += list(self.sources)
		params.append(int(limit))
		return frappe.db.sql(
			f"""select source_doctype, source_name, chunk_no, content, metadata,
				VEC_DISTANCE_COSINE(embedding, VEC_FromText(%s)) as distance
			from `{EMBEDDING_TABLE}` where {scope}
			order by distance limit %s""",
			params,
			as_dict=True,
		)

	def _may_read(self, row, meta: dict) -> bool:
		if self.conversation:
			return True
		if row.source_doctype == KNOWLEDGE_DOCTYPE:
			allowed = set(meta.get("visible_to_roles") or [])
			return not allowed or bool(allowed & set(frappe.get_roles()))
		if settings.is_blocked(row.source_doctype):
			return False
		try:
			return bool(frappe.has_permission(row.source_doctype, "read", doc=row.source_name))
		except frappe.DoesNotExistError:
			return False
