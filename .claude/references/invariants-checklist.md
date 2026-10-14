# Invariants checklist

Run through this list for every change. Each item maps to a CLAUDE.md rule or SPEC section. A "no" is a defect.

## The agent is the user (rules 1–2, SPEC §3, §7)
- [ ] Every tool reads and writes only through the calls in `permission-safe-tools.md`; none of the forbidden calls appear in `tools/`, `rag/store.py` retrieval filters, or `attachments/` reads.
- [ ] Tools rely on `frappe.session.user`, never on a user name from the model or from `TurnContext`.
- [ ] The job runner asserts that the session user owns the conversation before running a turn.
- [ ] `get_document` applies `check_permission("read")` and `apply_fieldlevel_read_permissions()`, and strips Password and hidden fields.
- [ ] Blocked DocTypes are refused by `guard.check` for every tool and are absent from `find_doctypes` and `describe_doctype` link targets.
- [ ] `read_only_mode` removes every write tool from the model's tool list.

## Writes need confirmation (rules 3–5, SPEC §7.2, §10)
- [ ] Every tool in `WRITE_TOOLS` is in `HumanInTheLoopMiddleware.interrupt_on`; there is no other path that changes user data during a turn.
- [ ] Each interrupt creates `AI Action Request` rows; only the conversation's user can decide them (checked server-side).
- [ ] After approval, `guard.check` runs again before the write.
- [ ] Every write adds the "Done by AI Assistant for <user>" timeline comment.
- [ ] Every tool call (ok or not) writes `AI Audit Log`; the row holds no document content.

## Cross-user isolation (SPEC §4.7–4.9, §4.14)
- [ ] `AI Conversation`, `AI Message`, `AI Attachment`, `AI Action Request` have owner-only `has_permission` + query hooks.
- [ ] Every endpoint loads conversation, attachment, and action request with `get_doc` + `check_permission`.
- [ ] Attachment chunks in `ai_embedding` are searched only with `conversation = <checked conversation>`.
- [ ] RAG results are filtered per document with `frappe.has_permission` after the vector search; knowledge documents by `visible_to_roles`.

## Secrets (rule 7)
- [ ] API keys are read only inside `llm/registry.py` / `llm/speech.py` / `observability/tracing.py` with `get_password`.
- [ ] No key, Password value, or `__Auth` data in graph state, checkpoints, `AI Message`, tool results, logs, realtime events, error messages, or LangSmith metadata.

## Models (rule 8, SPEC §6.3, §11.2)
- [ ] No hard-coded provider, model name, key, or token limit outside `install.after_install` defaults.
- [ ] User turns use `get_main_model()`; `get_evaluation_model()` is called only from `evals/`.
- [ ] Usage is logged per call with the right `purpose`; limits are checked before the call.

## Prompt injection (rule 10, SPEC §7.4)
- [ ] Tool results, attachment text, and transcripts are marked as data in the prompt and clipped to the configured limit.
- [ ] No code path turns content from a document, file, or transcript into an action without an `AI Action Request`.

## Files and voice (rules 16–18, SPEC §6.7–6.8)
- [ ] Uploads: extension allow-list, content sniffing, size, zip-bomb guard, private `File`, EXIF stripped.
- [ ] `File`s are read only after `check_permission("read")`, never by path or URL.
- [ ] No attachment bytes or base64 in graph state, checkpoints, or `AI Message`.
- [ ] Voice transcripts reach the agent as text only; the main model never receives the user's audio from a voice prompt.

## Evaluation (rule 15, SPEC §11.2)
- [ ] Runs only where `allow_tests` is on, as `evaluation_user`, with every write interrupt rejected.

## Server conventions (rule 11–13)
- [ ] Endpoints: `@frappe.whitelist(methods=[...])`, typed arguments, no `**kwargs`, Guest rejected, `enabled` and access checked first.
- [ ] GET endpoints never write.
- [ ] Append-only DocTypes are never updated or deleted outside the retention job.
- [ ] No imports from erpnext, hrms, crm, or frappe_whatsapp.

## Tests and docs
- [ ] New behaviour has a test on the test site; no test calls a real provider.
- [ ] SPEC sections, the CLAUDE.md diagram, and the module README match the change.
