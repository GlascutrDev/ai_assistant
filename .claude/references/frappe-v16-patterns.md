# Frappe v16 patterns for ai_assistant

Checked against the local source in `apps/frappe` (v16.51.0) on 2026-10-14. For anything not covered here, read the Frappe source rather than relying on memory.

## Desk routes
- Desk is served at **`/desk`**. `/app/...` only redirects there (`frappe/hooks.py` `website_redirects`). Use `/desk/<doctype-slug>/<name>` in links the assistant returns, and `/desk/ai-assistant` for the full-page chat.
- Desk JS is loaded on every Desk page with `app_include_js = "ai_assistant.bundle.js"` (file at `ai_assistant/public/js/ai_assistant.bundle.js`).

## Endpoints

```python
@frappe.whitelist(methods=["POST"])
def send_message(
	text: str,
	conversation: str | None = None,
	context: dict | None = None,
	attachments: list[str] | None = None,
	voice_attachment: str | None = None,
):
	access.require_user()
	conv = conversations.get_or_create(conversation, context)  # get_doc + check_permission inside
	return conversations.start_turn(conv, text, attachments, voice_attachment)
```

- `frappe.whitelist(allow_guest=False, xss_safe=False, methods=None)`. Always pass `methods`. POST auto-commits; **GET does not**, so GET endpoints never write.
- Frappe casts arguments by type hint. Never accept `**kwargs` from the client.
- `frappe.only_for("System Manager")` for Settings endpoints.
- Uploaded files: `frappe.request.files["file"]` (a Werkzeug `FileStorage`).

## Background jobs (verified)

```python
frappe.enqueue(
	"ai_assistant.agent.runner.run_turn",
	queue="long",
	job_id=f"ai-turn-{conv.name}",
	deduplicate=True,
	enqueue_after_commit=True,
	conversation=conv.name,
)
```

- `enqueue` stores `"user": frappe.session.user` in the job, and `execute_job` calls `frappe.set_user(user)` (`frappe/utils/background_jobs.py` lines ~179 and ~252). The job therefore runs **as the user who enqueued it**. The runner still asserts that the session user owns the conversation.
- `enqueue_after_commit=True` so the job sees the user message row.
- Queues: `short`, `default`, `long`. Turns use `long`; attachment processing uses `short`.

## Realtime (verified signature)

```python
frappe.publish_realtime(
	"ai_assistant_stream",
	{"conversation": conv, "type": "token", "text": delta},
	user=user,
	after_commit=False,   # streaming tokens: send now; the job commits only at the end
)
```

`publish_realtime(event, message, room=None, user=None, doctype=None, docname=None, task_id=None, after_commit=False)`. `user=` targets that user's room only. Use `after_commit=True` for events about saved rows (`confirmation`, `done`, `attachment_status`).

## Permission hooks

```python
# hooks.py
has_permission = {"AI Conversation": "ai_assistant.permissions.conversation_has_permission"}
permission_query_conditions = {"AI Conversation": "ai_assistant.permissions.conversation_query"}
```

- `def conversation_has_permission(doc, ptype=None, user=None) -> bool`: return **`True` to allow**. A falsy result, `None` included, denies.
- `def conversation_query(user) -> str`: a SQL WHERE fragment; escape with `frappe.db.escape`.

## Password fields
- `doc.get_password("api_key")` calls `get_decrypted_password(self.doctype, self.name, fieldname)`, so it works for any document with a name, child rows included (`frappe/model/base_document.py` ~1374). The value is stored in `__Auth` under the child DocType and row name. Still covered by a test in build step 1 (SPEC §4.2), because a Single's child rows are renamed on save.

## Files
- Private upload from code:

```python
file = frappe.get_doc({
	"doctype": "File",
	"file_name": safe_name,
	"content": data,
	"is_private": 1,
	"attached_to_doctype": "AI Conversation",
	"attached_to_name": conv.name,
}).insert()
```

- `File` permission (`frappe/core/doctype/file/file.py` `has_permission`): Administrator yes; **public files are readable by everyone**; the owner yes; shared yes; otherwise the permission of the attached document. So the agent may read any public file. Chat uploads are always private.
- Read content with `file.get_content()` after `file.check_permission("read")`. Never open paths from user input.

## Controllers
- Keep the auto-generated type block. Override only needed hooks. A docstring points to the parent: `"""See frappe.model.document.Document.validate."""`.

## Install and raw tables

```python
# hooks.py
after_install = "ai_assistant.install.after_install"
after_migrate = "ai_assistant.install.after_migrate"
```

`after_migrate` runs `CREATE TABLE IF NOT EXISTS` for `ai_checkpoint*` and `ai_embedding` (`.claude/references/mariadb-vector.md`). DDL commits implicitly in MariaDB; keep it out of request code.

## Scheduler

```python
scheduler_events = {
	"hourly": ["ai_assistant.tasks.expire_action_requests"],
	"daily": ["ai_assistant.tasks.purge_old_conversations", "ai_assistant.tasks.reindex_changed_sources"],
}
doc_events = {"*": {
	"on_update": "ai_assistant.rag.indexer.on_doc_change",
	"on_trash": "ai_assistant.rag.indexer.on_doc_trash",
	"after_rename": "ai_assistant.rag.indexer.on_doc_rename",
}}
```

`doc_events["*"]` runs for every save on the site: return at once unless the DocType is in the cached set of enabled sources.

## Tests

```python
from frappe.tests import IntegrationTestCase

class TestReadTools(IntegrationTestCase):
	def test_list_respects_user_permission(self):
		user = factories.assistant_user(user_permissions={"User": "a@example.com"})
		with self.set_user(user):
			result = read.list_documents.invoke({"doctype": "ToDo", "filters": {}})
		self.assertTrue(all(r["allocated_to"] == "a@example.com" for r in result["rows"]))
```

- Run tests on `today-test.localhost` only. `IntegrationTestCase` rolls back; tests must not commit.
- `UnitTestCase` (no database) for pure logic: extractors, serializers, prompt building.
