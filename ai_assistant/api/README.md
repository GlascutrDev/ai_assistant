# api

Whitelisted endpoints. Each one checks access first and then calls `services/` or `agent/`.

## Public API

| Endpoint | Method |
|---|---|
| `chat.send_message(text, conversation, context, attachments, voice_attachment)` | POST |
| `chat.decide_action(action_request, decision, edited_args, message)` | POST |
| `chat.cancel_turn(conversation)` | POST |
| `chat.list_conversations(limit, start)` | GET |
| `chat.get_conversation(conversation)` | GET |
| `chat.archive_conversation(conversation)` | POST |
| `chat.upload_attachment(conversation)` + multipart `file` | POST |
| `chat.remove_attachment(attachment)` | POST |
| `chat.transcribe(conversation)` + multipart `audio` | POST |
| `chat.get_bootstrap()` | GET |
| `settings.test_provider(label)` | POST, System Manager |
| `settings.run_evaluation(target_model)` | POST, System Manager |
| `settings.rebuild_index()` | POST, System Manager |

Realtime: `ai_assistant_stream` to the user's room, `type ∈ {token, step, tool_result, confirmation, attachment_status, done, error}`, always with `conversation`.

## Invariants

- `@frappe.whitelist(methods=[...])`, a type hint on every argument, no `**kwargs`.
- `access.require_user()` first (Guest, `enabled`, role), or `frappe.only_for("System Manager")`.
- Load conversations, attachments, and action requests through the services, which check ownership.
- GET endpoints never write.

## How to test

Call the functions directly inside `self.set_user(user)`. `frappe.enqueue(..., now=frappe.in_test)` runs the turn inline in tests.
