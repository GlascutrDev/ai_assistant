---
name: new-tool
description: Add or change an agent tool in ai_assistant/tools (read, write, file, or knowledge tool) so it runs as the signed-in user, passes guard.py, writes the audit log, and pauses for confirmation when it changes data. Use when asked to give the assistant a new ability or change what a tool returns.
---

# New agent tool

1. **Find it** in SPEC §7.1 (read) or §7.2 (write). If it is missing, confirm with the user, then add the row first.
2. **Read** CLAUDE.md rules 1–7, `.claude/references/permission-safe-tools.md`, and `.claude/references/langchain-v1-patterns.md` ("Tools").
3. **Write the tool** in `ai_assistant/tools/<area>.py`:
   - `@tool` with a docstring written for the model: what it does, when to use it, argument meaning, limits. The model reads this.
   - Type hints on every argument. Add `runtime: ToolRuntime[TurnContext]` only when it needs the conversation or limits.
   - First line of the body: `guard.check(tool_name, doctype=..., name=..., ptype=...)`. It refuses blocked DocTypes, read-only mode, and missing permission.
   - Read data only through the permission-applying APIs in the reference. Never `ignore_permissions`, `get_all`, `db.get_value`, `db.sql`.
   - Return a compact dict: the data, `truncated: bool`, and Desk links (`/desk/<doctype-slug>/<name>`). Cut it to `max_tool_result_chars` with `serialize.clip`.
   - Wrap the body with `audit.tool_call(...)` so every outcome (ok, permission_denied, blocked_doctype, validation_error, error) writes `AI Audit Log`.
4. **Register it** in `tools/__init__.py`: `READ_TOOLS` or `WRITE_TOOLS`. Write tools are added to `HumanInTheLoopMiddleware.interrupt_on` from that list, and are removed in `read_only_mode`.
5. **Write tools also:**
   - return a preview (`operation`, target, field diff) from `guard.preview(...)` for the confirmation card
   - re-run `guard.check` after approval
   - add the timeline comment "Done by AI Assistant for <user>" (SPEC §10)
6. **Tests** in `ai_assistant/tests/test_tools_<area>.py`, calling the tool directly (no LLM) inside `with self.set_user(...)`:
   - allowed path
   - permission denied (a user without the role) → no data in the result, audit `permission_denied`
   - blocked DocType → `blocked_doctype`
   - write tools: one scripted fake-LLM turn that pauses with an `AI Action Request`
   Use core DocTypes (`ToDo`, `Note`, `Contact`); ERPNext is not on the test site.
7. **Run** `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_tools_<area>` from `/home/nazmul/Desktop/AROMA` and report the real output.
8. **Docs:** SPEC §7 row, the tool list in the CLAUDE.md diagram, `ai_assistant/tools/README.md`. Add an evaluation example that uses the tool (`eval-case` skill).
