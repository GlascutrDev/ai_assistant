# tools

The agent's tools. Every tool runs as `frappe.session.user` and can never do more than that user can in Desk.

## Public API

| Name | Purpose |
|---|---|
| `READ_TOOLS`, `WRITE_TOOLS` | Registry (`__init__.py`). A tool in `WRITE_TOOLS` is interrupted for confirmation. |
| `for_turn(read_only)` | Tools offered to the model; `read_only_mode` drops every write tool |
| `guard.check(doctype, ptype, name)` | Blocked DocType, read-only mode, and `frappe.has_permission` pre-check |
| `base.execute(tool_name, body, ...)` | Runs a tool body: maps exceptions to outcomes, writes `AI Audit Log`, clips the result |
| `read.readable_document(doc)` | Values of a document the user may read (after `check_permission("read")`) |
| `serialize.clip(result)`, `serialize.desk_link(doctype, name)` | Size limit and `/desk/...` links |

| Area | Tools |
|---|---|
| meta | `find_doctypes`, `describe_doctype` |
| read | `list_documents`, `count_documents`, `aggregate`, `get_document`, `search_links`, `run_report` |
| knowledge | `search_knowledge` |
| files | `read_attachment`, `search_attachments` |
| spreadsheets | `inspect_spreadsheet`, `query_spreadsheet` (read); `write_spreadsheet` (write, confirmed; SPEC §6.8.1) |
| write | `create_document`, `update_document`, `submit_document`, `cancel_document`, `delete_document`, `add_comment`, `assign_to`, `apply_workflow_action`, `attach_file`, `write_spreadsheet`, `create_documents`, `update_documents`, `delete_documents` (`bulk.py`), `send_email` (`mail.py`), `remember`, `forget_memory` (`memory.py`) |

`preview.spec_of(name)` gives the card spec (operation, doctype, `precheck`, `preview`, `own_guard`, `by_name`) of the core tools that build their own card (`write_spreadsheet`, the bulk tools, `send_email`, the memory tools) and of extension write tools. `files.file_content(file, runtime)` reads a chat attachment or a record `File` with the `read_attachment` checks.

### Extension tools

`extension_tools()` loads the LangChain tools named in the `ai_assistant_read_tools` hook of installed apps (SPEC §7.5). `for_turn()` offers them with the read tools, also in read-only mode. Bad paths, objects that are not tools and duplicate names are skipped and logged.

`extension_write_tools()` loads the `ai_assistant_write_tools` hook. Each tool needs `metadata["ai_assistant"] = {"operation", "doctype", "precheck"?, "preview"?}`, or it is skipped and logged. `write_tool_names()` includes them, so they are interrupted for confirmation and removed in read-only mode. `write_spec(name)` returns the metadata. `preview.py` uses it for the card target, the pre-check (`guard.check` first) and the escaped `(headers, rows)` preview. `services.actions.operation_of(name)` gives the operation. `files.attachment_content(attachment, runtime)` gives an extension tool the bytes of the user's own chat attachment.

## Invariants

- Only the calls in `.claude/references/permission-safe-tools.md`. No `ignore_permissions`, `get_all`, `db.sql`, `db.get_value` on user-chosen DocTypes, `set_user`, or `get_password`.
- `guard.check` first. Blocked DocTypes (Settings, SPEC §7.3, every `AI *`) are refused and hidden from `find_doctypes` and link targets.
- Field names in `fields`, `filters`, `group_by`, and `order_by` must be readable at the user's permlevels.
- Password and hidden fields never leave a tool.
- Every call writes one `AI Audit Log` row through `base.execute`, also when it is denied or fails.
- A failed call returns `{"error": <reason>}`: the app's own text for validation and 4xx Frappe errors, and `base.SYSTEM_ERROR` (with an Error Log) for anything else. A successful call adds the app's `msgprint` warnings as `messages`.
- The `runtime` argument is optional and hidden from the model, so tests call tools directly with `.invoke({...})`.

## How to test

- `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_extension_tools`

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_tools_read
```

Use core DocTypes (`ToDo`, `Note`) and `factories.assistant_user(...)` with `self.set_user(user)`. A new tool needs: the allowed path, the permission-denied path, the blocked-DocType path, and one scripted fake-LLM turn.
