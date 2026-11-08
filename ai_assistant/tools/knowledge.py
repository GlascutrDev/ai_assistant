"""search_knowledge (SPEC §7.1, §8.3)."""

import frappe
from frappe import _
from langchain.tools import ToolRuntime, tool

from ai_assistant.agent import context as turn
from ai_assistant.llm import registry
from ai_assistant.rag import indexer
from ai_assistant.rag.store import FrappeVectorStore
from ai_assistant.services import agents, settings
from ai_assistant.tools import base, serialize


@tool
def search_knowledge(query: str, runtime: ToolRuntime = None) -> dict:
	"""Search the company knowledge base (how-to notes, policies, SOPs) and indexed records by meaning.
	Use it for "how do I…", "what is our policy…", or to find records by description."""
	return base.execute(
		"search_knowledge", lambda: _search(query, runtime), args={"query": query}, runtime=runtime
	)


def _search(query: str, runtime=None) -> dict:
	if not indexer.is_searchable():
		frappe.throw(_("The knowledge base is not available right now."))
	sources = agents.knowledge_scope(turn.of(runtime).agent)
	store = FrappeVectorStore(registry.get_embeddings(), sources=sources)
	results = []
	for doc, distance in store.similarity_search_with_score(query, k=settings.get().top_k or 6):
		meta = doc.metadata
		link = (
			None
			if meta["source_doctype"] == "AI Knowledge Document"
			else serialize.desk_link(meta["source_doctype"], meta["source_name"])
		)
		results.append(
			{
				"source": meta["source_doctype"],
				"name": meta["source_name"],
				"title": meta.get("title"),
				"link": link,
				"relevance": round(1 - distance, 3),
				"text": doc.page_content,
			}
		)
	return {"query": query, "results": results}
