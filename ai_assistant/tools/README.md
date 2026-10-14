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
| write | `create_document`, `update_document`, `submit_document`, `cancel_document`, `delete_document`, `add_comment`, `assign_to`, `apply_workflow_action`, `attach_file` |

## Invariants

- Only the calls in `.claude/references/permission-safe-tools.md`. No `ignore_permissions`, `get_all`, `db.sql`, `db.get_value` on user-chosen DocTypes, `set_user`, or `get_password`.
- `guard.check` first. Blocked DocTypes (Settings, SPEC §7.3, every `AI *`) are refused and hidden from `find_doctypes` and link targets.
- Field names in `fields`, `filters`, `group_by`, and `order_by` must be readable at the user's permlevels.
- Password and hidden fields never leave a tool.
- Every call writes one `AI Audit Log` row through `base.execute`, also when it is denied or fails.
- The `runtime` argument is optional and hidden from the model, so tests call tools directly with `.invoke({...})`.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_tools_read
```

Use core DocTypes (`ToDo`, `Note`) and `factories.assistant_user(...)` with `self.set_user(user)`. A new tool needs: the allowed path, the permission-denied path, the blocked-DocType path, and one scripted fake-LLM turn.
