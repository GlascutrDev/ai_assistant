---
name: new-doctype
description: Create or change an AI DocType in ai_assistant from its SPEC §4 definition — JSON, thin controller, permission hooks, factory, tests, docs. Use when asked to build or change AI Assistant Settings, AI Conversation, AI Message, AI Attachment, AI Action Request, AI Audit Log, AI Usage Log, AI Evaluation Run, or a child table.
---

# New or changed AI DocType

Input: a DocType from SPEC §4, or a field change. If it is not in SPEC §4, stop and ask; don't invent the schema.

1. **Read** the SPEC §4 entry and every SPEC section that uses its fields (grep the DocType name). For generic JSON keys, load the vendored `frappe-app-dev/references/doctypes.md`.
2. **Prerequisites.** Developer mode on and the app installed on both sites (the SessionStart hook reports this). Otherwise give the user the command and stop.
3. **JSON** at `ai_assistant/ai_assistant/doctype/ai_<snake>/ai_<snake>.json` plus an empty `__init__.py`. Don't create other files by hand; migrate generates them.
   - `"module": "Ai Assistant"`, `"name": "AI <Name>"`; `issingle: 1` for Settings; `istable: 1` for child tables
   - fields in SPEC order; Select options verbatim from SPEC; `search_index: 1` on `user`, `conversation`, `status`, `date`
   - API keys and other secrets: `fieldtype: "Password"`, never Data
   - append-only DocTypes (`AI Message`, `AI Audit Log`, `AI Usage Log`): all fields `read_only`, no write/delete permission for any role, `track_changes: 0`
   - per-user DocTypes (`AI Conversation`, `AI Message`, `AI Attachment`, `AI Action Request`): `AI Assistant User` with `if_owner: 1`; System Manager read
4. **Permission hooks** for per-user DocTypes in `ai_assistant/permissions.py`, registered in `hooks.py` `has_permission` and `permission_query_conditions`. A `has_permission` hook returns `True` to allow; `None` denies (`.claude/references/frappe-v16-patterns.md`).
5. **Controller** `ai_<snake>.py`: keep the auto-generated type block; override only what SPEC needs and delegate to `services/`. A docstring points to the parent: `"""See frappe.model.document.Document.validate."""`.
6. **Factory** in `ai_assistant/tests/factories.py`.
7. **Tests** in `test_ai_<snake>.py` (`IntegrationTestCase`): each validation rule, plus "user B cannot read user A's record" for per-user DocTypes, plus "update/delete refused" for append-only ones.
8. **Migrate and test** from `/home/nazmul/Desktop/AROMA`:
   `bench --site today.localhost migrate && bench --site today-test.localhost migrate`, then
   `bench --site today-test.localhost run-tests --doctype "AI <Name>"`. Report the real output.
9. **Docs:** CLAUDE.md diagram (new DocType), `ai_assistant/ai_assistant/doctype/README.md` row, SPEC §4 **[Decision]** if the build forced a choice.
