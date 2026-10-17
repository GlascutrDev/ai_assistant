# services

Business logic behind the thin entry points (`api/`, controllers, `tasks.py`). One file per concern.

## Public API

| Module | Purpose |
|---|---|
| `settings` | `get()`, `blocked_doctypes()`, `is_blocked()`, `allowed_file_types()`, `max_rows()`, `find_profile()` |
| `access` | `require_user()` (Guest, `enabled`, role), `has_access()`, `is_admin()` |
| `budget` | `assert_available()` (daily tokens per user), `assert_site_budget()` (monthly cost), `add()` |
| `conversations` | `load_own()`, `get_or_create()`, `start_turn()` (one turn per thread), `enqueue_turn()`, `add_message()`, `payload()` |
| `actions` | AI Action Request: `create_from_interrupt()`, `decide()`, `resume_if_complete()`, `reject_open()`, `expire_stale()` |
| `attachments` | AI Attachment lifecycle: `create()`, `process()` (queue short), `for_message()`, `remove()`, `purge_old()` |
| `voice` | `transcribe()` a recording into an editable transcript |
| `audit` | `tool_call()` writes one AI Audit Log row |
| `catalog` | Cached DocType metadata for `find_doctypes` |
| `bootstrap` | `get()` returns what the chat UI needs at start |
| `append_only` | `AppendOnlyDocument` mixin for AI Message, AI Audit Log, AI Usage Log |

## Invariants

- `load_own()` in `conversations` and `attachments` refuses another user's records. Use it for every lookup by name.
- Only the conversation's user decides its action requests. `actions.decide()` checks this, not the JS (CLAUDE.md rule 4).
- Audit rows hold an argument hash, never document content.
- Append-only rows change only when `frappe.flags.ai_assistant_purge` is set by the retention job.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_actions
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_settings
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_voice
```
