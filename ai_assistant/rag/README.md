# rag

Permission-aware retrieval over the knowledge sources (SPEC §8).

## Public API

| Name | Purpose |
|---|---|
| `store.FrappeVectorStore(embeddings, conversation=None)` | LangChain `VectorStore` over `ai_embedding`. `conversation=None` searches knowledge chunks; a conversation name searches that conversation's attachment chunks. |
| `store.similarity_search_with_score(query, k)` | Over-fetches ×4, drops chunks the session user may not read, returns the first `k` |
| `indexer.sync(doctype, name)` | Replace one document's chunks (background job) |
| `indexer.rebuild_all()` | Recreate the table with the profile's dimensions and index every source; clears `index_stale` |
| `indexer.on_doc_change/on_doc_trash/on_doc_rename` | `doc_events["*"]` hooks; return at once unless the DocType is an enabled source |
| `indexer.is_searchable()` | RAG on, index not stale, table dimensions match the embedding profile |
| `loaders.text_of(doc, content_fields)` | Text of a source document |

## Invariants

- Never return a chunk without the per-document check: `frappe.has_permission(source_doctype, "read", source_name)`, blocked DocTypes dropped, knowledge documents by `visible_to_roles`.
- Attachment chunks (`conversation` set) are searched only with a conversation the caller has already checked.
- A change of embedding model or dimensions sets `index_stale`; search is off until `rebuild_all` finishes.
- Raw SQL only on `ai_embedding`, always with parameters.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_rag
```

The test recreates `ai_embedding` with 8 dimensions (fake embeddings) on the test site.
