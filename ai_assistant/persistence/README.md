# persistence

LangGraph checkpoint storage in MariaDB, plus the raw tables that DocType JSON cannot declare.

## Public API

| Name | Purpose |
|---|---|
| `checkpointer.FrappeCheckpointSaver()` | `BaseCheckpointSaver` on `ai_checkpoint`, `ai_checkpoint_blob`, `ai_checkpoint_write` |
| `schema.ensure_tables()` | `CREATE TABLE IF NOT EXISTS` for the checkpoint tables and `ai_embedding`. Called from `after_install` and `after_migrate`. |
| `schema.create_embedding_table(dim, drop=False)` | (Re)create `ai_embedding` with `VECTOR(dim)` |
| `dblock.LOCK` | Process-wide `RLock` for `frappe.db` use inside a graph run |

## Invariants

- The saver writes through `frappe.db`, inside the caller's transaction. The job runner commits; the saver never commits.
- LangGraph runs checkpoint writes and parallel tool calls in worker threads that share the job's DB connection. Every query made inside a graph run holds `dblock.LOCK`.
- `frappe.db.sql` decodes the query as UTF-8, so binary blobs are sent as hex and stored with `UNHEX()`.
- Implements the base capabilities only (`put`, `put_writes`, `get_tuple`, `list`, `delete_thread`). The retention job removes a conversation's checkpoints with `delete_thread`.
- DDL commits implicitly. Keep it in install hooks and the index rebuild job, never in request code.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_checkpointer
```

The test runs `langgraph.checkpoint.conformance` (dev dependency `langgraph-checkpoint-conformance`) and an interrupt/resume with a new saver instance.
