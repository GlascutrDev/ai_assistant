# services

Business logic behind the thin entry points (`api/`, controllers, `tasks.py`). One file per concern.

## Public API

| Module | Purpose |
|---|---|
| `settings` | `get()`, `blocked_doctypes()`, `is_blocked()`, `allowed_file_types()`, `max_rows()`, `find_profile()` |
| `access` | `require_user()` (Guest, `enabled`, role), `has_access()`, `is_admin()` |
| `budget` | `assert_available()` (daily tokens per user), `assert_site_budget()` (monthly cost), `add()` |
| `conversations` | `load_own()`, `get_or_create()`, `start_turn()` (one turn per thread), `enqueue_turn()`, `add_message()`, `payload()` |
| `actions` | AI Action Request: `create_from_interrupt()`, `decide()`, `resume_if_complete()` (web requests only), `decisions_for()`, `reject_open()`, `expire_stale()` |
| `attachments` | AI Attachment lifecycle: `create()`, `process()` (queue short), `for_message()`, `remove()`, `purge_old()` |
| `voice` | `transcribe()` a recording into an editable transcript |
| `audit` | `tool_call()` writes one AI Audit Log row |
| `catalog` | Cached DocType metadata for `find_doctypes` |
| `bootstrap` | `get()` returns what the chat UI needs at start |
| `append_only` | `AppendOnlyDocument` mixin for AI Message, AI Audit Log, AI Usage Log |
| `memory` | AI Memory (SPEC §6.9): `validate()` (controller), `remember()`, `forget()`, `own()`, `from_feedback()`, `prompt_block(user)` |
| `feedback` | AI Feedback: `rate(message, rating, comment)` (a Down comment also saves a memory), `ratings_for(conversation)` |
| `automations` | AI Automation (SPEC §6.10): `validate()`, `check_cron()`, `is_due()`, `run_due()` (scheduler), `on_doc_event()` (doc_events), `matches()` as the owner |
| `agents` | AI Agent (SPEC §6.11): `validate()`, `can_use()`, `available(user)`, `resolve(name)` (new conversation), `load(name)` (every turn; raises `AgentUnavailableError`), `filter_tools()`, `knowledge_scope()`, `prompt_block()` |
| `automation_run` | `run(automation, doctype, docname)`: background job; switches to the owner, one turn in a new conversation, then notification, email or `Waiting for approval` |

## Invariants

- `load_own()` in `conversations` and `attachments` refuses another user's records. Use it for every lookup by name.
- Only the conversation's user decides its action requests. `actions.decide()` checks this, not the JS (CLAUDE.md rule 4).
- Audit rows hold an argument hash, never document content.
- Append-only rows change only when `frappe.flags.ai_assistant_purge` is set by the retention job.
- Personal memories are written only by their user; Shared ones only by a System Manager. The model never writes Shared memory.
- An agent only removes tools and knowledge; it never adds a tool, a permission or a model.
- An automation runs as its owner only (`automation_run.run` is the only `frappe.set_user`), its writes still wait for approval, and changes made during a run (`frappe.flags.ai_automation`) start no automation.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_actions
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_settings
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_voice
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_memory_feedback
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_automations
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_bulk_email
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_agents
```
