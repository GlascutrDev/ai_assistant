# Permission-safe Frappe calls for agent tools

The agent acts as `frappe.session.user`. Every tool reads and writes only through calls that apply that user's permissions. Checked against `apps/frappe` v16.51.0.

## Allowed

| Need | Call | What Frappe checks |
|---|---|---|
| Can the user read a DocType at all | `frappe.has_permission(doctype, "read")` | role permissions |
| Readable fields of a DocType | `frappe.get_meta(doctype).get_permitted_fieldnames(permission_type="read")` | permlevels the user has |
| List rows | `frappe.get_list(doctype, filters=..., fields=..., order_by=..., limit_page_length=n)` | role, user permissions, `if_owner`, shares, `permission_query_conditions` hooks |
| Count | `frappe.get_list(doctype, filters=..., fields=[{"COUNT": "*", "as": "count"}])` | same as above |
| Aggregate | `frappe.get_list(doctype, filters=..., fields=["status", {"SUM": "grand_total", "as": "total"}], group_by="status")` | same; functions allowed: see `FUNCTION_MAPPING` in `frappe/database/query.py` |
| One document | `doc = frappe.get_doc(doctype, name); doc.check_permission("read"); doc.apply_fieldlevel_read_permissions()` | document permission + `has_permission` hooks; removes fields above the user's permlevels and applies field masks |
| Report | `frappe.desk.query_report.run(report_name, filters=...)` | report roles and the ref DocType |
| Link search | `frappe.desk.search.search_widget(doctype, txt, page_length=20)` | user permissions on the DocType |
| Create | `frappe.get_doc({...}).insert()` | create permission, mandatory fields, validations, user permissions on links |
| Update | `doc.check_permission("write")`, set values, `doc.save()` | write permission, permlevel on changed fields |
| Submit / cancel | `doc.submit()` / `doc.cancel()` | submit / cancel permission |
| Delete | `frappe.delete_doc(doctype, name)` | delete permission (`ignore_permissions` defaults to False) |
| Workflow | `frappe.model.workflow.apply_workflow(doc, action)` | allowed transitions for the user's roles |
| Assign | `frappe.desk.form.assign_to.add({"assign_to": [...], "doctype": ..., "name": ..., "description": ...})` | read permission on the doc |
| File | `file = frappe.get_doc("File", name); file.check_permission("read"); file.get_content()` | owner / share / attached doc (public files: everyone) |

After reading a document, also drop:
- fields with `fieldtype == "Password"` (and never call `get_password` in a tool)
- fields with `hidden == 1` unless the user asked for them by name and has the permlevel

## Forbidden in anything the agent can reach

| Call | Why |
|---|---|
| `ignore_permissions=True`, `frappe.flags.ignore_permissions = True` | bypasses every check |
| `frappe.get_all`, `frappe.db.get_all` | `get_list` without permissions |
| `frappe.db.get_value`, `frappe.db.get_values`, `frappe.db.count`, `frappe.db.exists` on user-requested DocTypes | no permission check; leaks existence and values |
| `frappe.db.sql`, `frappe.qb` on user-requested DocTypes | no permission check; injection risk |
| `frappe.db.set_value`, `doc.db_set` | skips validation and permission |
| `frappe.set_user`, `frappe.session.user = ...` | changes who the agent is |
| `frappe.call`, `frappe.get_attr` with model-chosen names | runs arbitrary methods |
| `eval`, `exec`, `safe_exec`, `subprocess` | code execution |

Internal services that are **not** reachable by the model (e.g. writing `AI Audit Log`, `AI Usage Log`, checkpoint rows) may use `ignore_permissions=True`, because the user must not be able to edit those rows. Keep such code out of `tools/`.

## Guard order in each tool

1. `guard.check(tool, doctype, name, ptype)`:
   - `doctype` not in blocked list (Settings + SPEC §7.3 defaults + every `AI *` DocType)
   - `read_only_mode` off for writes
   - `frappe.has_permission(doctype, ptype, name)` (cheap pre-check, so the confirmation card never offers a doomed action)
2. The allowed call above (which checks again, authoritatively).
3. `serialize.clip(result, max_tool_result_chars)`.
4. `audit.tool_call(...)` with the outcome. Map exceptions: `frappe.PermissionError` → `permission_denied`, `frappe.ValidationError` → `validation_error` (return its message to the model), anything else → `error` (generic message to the model; details in the audit row).
