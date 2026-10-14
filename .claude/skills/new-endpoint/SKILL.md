---
name: new-endpoint
description: Add or change an ai_assistant.api endpoint (chat or settings) per SPEC §12 — whitelisting, type hints, access checks, enqueueing turns, realtime events, tests, and the Desk JS caller. Use when asked to add or change an API method of the assistant.
---

# New ai_assistant.api endpoint

1. **Find it** in SPEC §12. If it is missing, confirm with the user, then add the row first.
2. **Read** CLAUDE.md rule 11 and `.claude/references/frappe-v16-patterns.md` ("Endpoints", "Background jobs", "Realtime").
3. **Write it** in `ai_assistant/api/chat.py` or `api/settings.py`. Keep it thin:
   1. `@frappe.whitelist(methods=["POST"])` for changes, `["GET"]` for reads. A type hint on every argument; no `**kwargs`.
   2. `access.require_user()`: rejects Guest, checks `enabled` and the role (SPEC §3). Settings endpoints call `frappe.only_for("System Manager")`.
   3. Load the conversation/attachment/action request with `frappe.get_doc` + `check_permission`, so user B can never pass user A's names.
   4. Call a function in `services/` (or `agent.runner` via `frappe.enqueue`). Model calls never run inside the request, except `transcribe` (SPEC §6.7).
   5. GET endpoints never write: GET does not commit.
4. **Uploads** (`upload_attachment`, `transcribe`): read `frappe.request.files`, then call `attachments/upload.py` for the type, sniffing, and size checks before any `File` is saved.
5. **Realtime:** `frappe.publish_realtime("ai_assistant_stream", {...,"conversation": name}, user=user, after_commit=True)`. Never the site room.
6. **Tests** in `ai_assistant/tests/test_api_<area>.py`:
   - happy path
   - Guest and a user without access → `PermissionError`
   - user B with user A's conversation → `PermissionError`
   - assistant disabled → refused
   Patch `frappe.enqueue` or run jobs inline; use `tests/fake_llm.py`.
7. **Run** `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_api_<area>` and report the real output.
8. **Caller** in `ai_assistant/public/js/chat/api.js` with `frappe.call({method: "ai_assistant.api.<area>.<name>", type: "POST", args})`.
9. **Docs:** SPEC §12 row, `ai_assistant/api/README.md`.
