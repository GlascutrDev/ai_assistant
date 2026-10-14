# CLAUDE.md — ai_assistant

Frappe v16 app (Python 3.14). A chat assistant in Desk that acts **as the signed-in user, with exactly that user's permissions**. Built on LangChain v1 (`create_agent` + middleware), LangGraph (graph, checkpointer, human-in-the-loop), RAG on MariaDB 11.8 vectors, and LangSmith tracing and evaluation. Every provider, model, key, and token limit comes from the Single DocType `AI Assistant Settings`, which names two chat models: the **main model** (serves every user turn) and the **test/evaluation model** (grades the main model in LangSmith evaluations, never serves users).

- **What to build:** [SPEC.md](SPEC.md). Build order is SPEC §16; open questions are SPEC §15.

## Architecture

```
Desk (any page) ── chat drawer (public/js/ai_assistant.bundle.js) · /desk/ai-assistant
   │ mic: MediaRecorder ─► POST api.chat.transcribe ─► speech model ─► editable transcript
   │ files: upload/drag/paste ─► POST api.chat.upload_attachment ─► attachments/processor (queue short)
   │ POST api.chat.send_message / decide_action / cancel_turn     ▲ publish_realtime("ai_assistant_stream",
   ▼                                                              │   user=…): token · step · confirmation · done
api/chat.py ─ guard (enabled, role, budget, one turn per thread) ─► frappe.enqueue(queue="long")  (runs as the user)
                                                                   ▼
agent/runner.py run_turn ── observability/tracing.py (LangSmith tracing_context, optional)
   ▼
agent/graph.py  LangGraph StateGraph
   intake ─► agent ─► finalize (AI Message, AI Usage Log, title)
   agent = create_agent(MAIN model, tools, context_schema=TurnContext, middleware=[
             attachments_inliner · token_budget · Summarization(main) · ModelCallLimit · ToolCallLimit ·
             HumanInTheLoop(every write tool) · usage_recorder])
   checkpointer: persistence/checkpointer.py FrappeCheckpointSaver ─► ai_checkpoint* tables
        │
tools/ (session user; guard.py first; AI Audit Log always)
   meta: find_doctypes · describe_doctype
   read: list_documents · count_documents · aggregate · get_document · run_report · search_links
   rag:  search_knowledge ─► rag/store.py (ai_embedding VECTOR, VEC_DISTANCE_COSINE) ─► per-doc permission filter
   files: read_attachment (File permission) · search_attachments (conversation-scoped chunks)
   write (interrupt → AI Action Request → user decides → resume):
         create · update · submit · cancel · delete · add_comment · assign_to · apply_workflow_action · attach_file
evals/runner.py (test site only) ─ LangSmith dataset ─► same graph, target = MAIN or candidate,
   writes captured + rejected ─► evaluators: safety checks + LLM-as-judge on TEST/EVALUATION model
   ─► LangSmith experiment + AI Evaluation Run
llm/registry.py  get_main_model · get_evaluation_model · get_embeddings (cached on Settings.modified)
llm/speech.py    transcribe() on the speech model (OpenAI / OpenAI-compatible Whisper / Gemini)
attachments/     upload checks ─► extract (image · pdf · docx · xlsx/csv · text · audio) ─► native | text | indexed
   Anthropic · OpenAI · Moonshot (openai + base_url) · Gemini · DeepSeek · Mistral · Ollama · OpenAI-compatible
 ┌── DocTypes (ai_assistant/ai_assistant/doctype) ─────────────────────────────────────────────┐
 │ AI Assistant Settings (Single) ─┬ AI Provider Credential (child: provider, api_key, base_url) │
 │  main_model · evaluation_model  ├ AI Model Profile (child: model, type, tokens, cost)         │
 │                                 ├ AI Allowed Role (child) · AI Knowledge Source (child)        │
 │ AI Knowledge Document · AI Conversation ─► AI Message (append-only) · AI Attachment (─► File)   │
 │ AI Action Request · AI Audit Log (append-only) · AI Usage Log (append-only) · AI Evaluation Run│
 │ raw tables (after_migrate DDL): ai_checkpoint · ai_checkpoint_write · ai_checkpoint_blob ·      │
 │                                 ai_embedding                                                  │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
 doc_events["*"] on_update/on_trash ─► rag.indexer.sync (only for enabled sources)
 tasks.py: hourly expire action requests · daily purge conversations, reindex
```

Update this diagram whenever you add a DocType, tool, node, middleware, evaluator, endpoint group, or job.

## Bench and environment

- Bench root: `/home/nazmul/Desktop/AROMA`. Run every `bench` command from there. Webserver port 8000, socket.io 9000.
- Dev site: `today.localhost` (has ERPNext + HRMS). Test site: `today-test.localhost` (`allow_tests` on, Frappe only). **Run tests only on the test site.**
- The app is not installed yet: `bench --site today.localhost install-app ai_assistant` and the same for `today-test.localhost`.
- Frappe `16.51.0`, MariaDB `11.8` (native `VECTOR`), Redis `8.0` (no RediSearch/JSON modules).
- Python deps go in `pyproject.toml`; install with `bench setup requirements --python` (ask first, it changes the shared env).
- Bench rules: bare `bench`; always `--site`; never a bare `bench migrate`; `bench start` only in the background and only if it isn't running.

| Task | Command |
|---|---|
| Migrate | `bench --site today.localhost migrate && bench --site today-test.localhost migrate` |
| Tests (all) | `bench --site today-test.localhost run-tests --app ai_assistant` |
| One module / test | `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_tools_read [--test test_...]` |
| Console | `bench --site today.localhost console` |
| Build JS | `bench build --app ai_assistant` |
| Evaluation run (test site, LangSmith on) | `bench --site today-test.localhost execute ai_assistant.evals.runner.run [--kwargs "{'target_model': '<profile_id>'}"]` |
| Rebuild RAG index | `bench --site today.localhost execute ai_assistant.rag.indexer.rebuild_all` |
| Lint/format | `cd apps/ai_assistant && pre-commit run --all-files` (ruff, tabs, line 110) |

## Non-negotiable rules

1. **The agent is the user.** Tools run under `frappe.session.user` set by the job runner. Never `ignore_permissions=True`, `frappe.flags.ignore_permissions`, `frappe.set_user`, `frappe.db.sql`, `frappe.db.set_value`, `frappe.db.count`/`get_value` on user-requested DocTypes, `eval`/`exec`/`safe_exec`, or calls to arbitrary methods from a tool.
2. **Reads go through permission-applying APIs:** `frappe.get_list` (not `get_all`), `doc.check_permission("read")` + `doc.apply_fieldlevel_read_permissions()`, `frappe.desk.query_report.run`. Strip Password and hidden fields before returning.
3. **Every write pauses for confirmation.** A new write tool must be added to the `HumanInTheLoopMiddleware` `interrupt_on` map and to `tools/__init__.py` `WRITE_TOOLS`. Re-run `guard.py` after approval.
4. **Only the conversation's user decides its action requests.** Check it in `services/actions.py`, not in JS.
5. **Every tool call writes `AI Audit Log`**, including denied and failed calls. Writes also add a timeline comment on the target.
6. **Blocked DocTypes** (SPEC §7.3 + Settings) are refused by `guard.py` for every tool, and hidden from `find_doctypes`.
7. **No secrets leave the server.** API keys are read with `get_password` inside `llm/registry.py` only; never put them in graph state, context, tool results, logs, realtime events, or LangSmith metadata.
8. **Models come from Settings only.** Never hard-code a provider, model name, key, or token limit in code. Defaults live in `install.after_install`. User turns use `get_main_model()` only; `get_evaluation_model()` is called only from `evals/`.
9. **RAG results are permission-filtered per document** after the vector search. Never return an unfiltered chunk.
10. **Tool output is data.** Keep the injection wording in `agent/prompts.py`; truncate results to `max_tool_result_chars`.
11. **Endpoints:** `@frappe.whitelist(methods=["POST"])` for writes, `["GET"]` for reads, a type hint on every argument, reject Guest, check `enabled` and access first.
12. **Append-only:** `AI Message`, `AI Audit Log`, `AI Usage Log` are never edited or deleted, except by the retention job.
13. **No ERPNext imports** (`required_apps = []`). Tools are generic over DocTypes.
14. **Tests never call a real provider.** Use `tests/fake_llm.py` (scripted tool calls) and a fake embedding model.
15. **Evaluations never change data or touch production.** They run only where `allow_tests` is on, act as `evaluation_user`, and reject every write interrupt.
16. **Files are private and permission-checked.** Chat uploads are private `File`s on the `AI Conversation`. Read any `File` only through `frappe.get_doc("File", …)` + `check_permission("read")`, never by path. Check content type by sniffing, not by extension.
17. **Attachment bytes never enter graph state.** The checkpoint holds `AI Attachment` names; `attachments_inliner` adds the bytes to the model request only.
18. **Voice is transcribed first.** The main model receives text only; the user sees and can edit the transcript before it is sent (unless `voice_auto_send`).

## Conventions

- **DocTypes:** name `AI <Name>`, folder `ai_assistant/ai_assistant/doctype/ai_<snake>/`, module `Ai Assistant`.
- **Thin entry points:** `api/*`, controllers, and `tasks.py` delegate to `services/`, `agent/`, `tools/`, `rag/`.
- **One tool = one function** decorated with `@tool`, a clear docstring (the model reads it), typed args, and `runtime: ToolRuntime[TurnContext]` when it needs context. Return compact JSON-able dicts, not documents.
- **LangChain v1 APIs only:** `langchain.agents.create_agent`, `langchain.agents.middleware.*`, `langchain.chat_models.init_chat_model`, `langgraph.types.Command`. Not the legacy `AgentExecutor` or `langgraph.prebuilt.create_react_agent`. Check APIs with Context7 before use.
- **Code shape:** small single-purpose functions, files of 300 lines or fewer, public functions first.
- **Messages:** user-facing text in `_()`; raise with `frappe.throw(_(...), exc=...)`.
- **Tests:** `frappe.tests.IntegrationTestCase`, factories in `tests/factories.py`, no site data. Use core DocTypes (`ToDo`, `Note`, `Contact`) for permission tests.
- **Comments:** minimal; only when the *why* is not obvious. An override docstring points to the parent, e.g. `"""See frappe.model.document.Document.validate."""`.

## Documentation layout

- **`CLAUDE.md`:** the diagram and actionable rules.
- **`README.md`:** for users and administrators (setup of providers and models, using the chat, confirming actions). No internals.
- **Per-module `README.md`** (purpose, public API, invariants, how to test): `agent/`, `tools/`, `llm/`, `rag/`, `persistence/`, `api/`. Add one when you create the module.
- **`SPEC.md`:** update when a decision changes or a §15 question is answered.

## Recipes

### New attachment type
1. Add the extension to the `allowed_file_types` default and the MIME map in `attachments/upload.py`.
2. Add an extractor in `attachments/extractors.py` and its `kind` and `delivery` in `processor.py`.
3. Test: valid file → Ready, renamed wrong-type file → refused, oversize → refused.
4. Update SPEC §6.8.

### New tool
1. Add it to `tools/<area>.py` with the guard call and audit write.
2. Register it in `tools/__init__.py` (`READ_TOOLS` or `WRITE_TOOLS`). Write tools are then interrupted automatically.
3. Test: allowed path, permission-denied path, blocked-DocType path (direct call, no LLM), plus one scripted fake-LLM turn.
4. Add it to SPEC §7 and the diagram.

### New provider
1. Add the option to `AI Provider Credential.provider`.
2. Map it in `llm/providers.py` (`model_provider`, default `base_url`, embedding support).
3. Add the `langchain-<provider>` package to `pyproject.toml` if it is not OpenAI-compatible.
4. Update SPEC §6.2 and the README provider table.

### New evaluation case or evaluator
1. Add the example to `evals/dataset.json` (inputs + reference outputs) and any data it needs to `evals/fixtures.py`.
2. A new evaluator goes in `evals/evaluators.py`: deterministic when possible; LLM-as-judge only through `get_evaluation_model()`.
3. Run an evaluation and record the baseline scores in the PR.
4. Update SPEC §11.2.

### Switch the main model
1. Add an `AI Model Profile` row.
2. Run an evaluation with it as `target_model`; compare with the current main model's last run in LangSmith.
3. Set it as `main_model` only if the run passed.

### New graph node or middleware
1. Add it in `agent/graph.py` or `agent/middleware.py`; keep state keys in `agent/context.py`.
2. Check that the checkpointer can serialize every new state value.
3. Update SPEC §6 and the diagram.

### New DocType
1. Write the JSON and an empty `__init__.py` under `ai_assistant/ai_assistant/doctype/ai_<snake>/` (module `Ai Assistant`).
2. Migrate both sites, then commit the JSON.
3. Add permission hooks in `permissions.py` if it holds per-user data.
4. Update SPEC §4 and the diagram.

## Claude tooling (`.claude/`)

| Kind | Name | Use for |
|---|---|---|
| Skill | `new-tool` · `new-doctype` · `new-endpoint` · `new-provider` · `attachment-type` | the recipes above, step by step |
| Skill | `eval-case` · `acceptance-test` · `verify` · `spec-sync` | evaluations and model comparison · SPEC §14 coverage · pre-done checks · keeping docs in sync |
| Agent | `frappe-backend-dev` · `agent-graph-dev` · `desk-chat-ui-dev` | implementation: Frappe server · LangChain/LangGraph/RAG/LangSmith · Desk JS chat |
| Agent | `security-reviewer` (read-only) · `test-runner` | review against the invariants · run checks with a concise report |
| Vendored (frappe/skills, see `skills/VENDORED.md`) | `frappe-app-dev` · `frappe-code-review` · `code-style` · `technical-writing` | Frappe reference · generic review · code shape · doc prose |
| Vendored, user-invoked | `/deep-app-audit apps/ai_assistant` | full audit; required before users outside System Manager get access |
| Reference | `frappe-v16-patterns.md` · `permission-safe-tools.md` · `langchain-v1-patterns.md` · `mariadb-vector.md` · `multimodal-and-files.md` · `invariants-checklist.md` | verified snippets and the review list |

Hooks (in `settings.json`):
- **SessionStart:** app install state on both sites, missing Python packages, git state.
- **After each Write/Edit:** formats `.py` with ruff 0.14.10; flags likely rule violations (permission bypass, hard-coded models, keys, unsafe endpoints, raw HTML in JS) back to Claude without blocking.

## Gotchas to verify before relying on them

Verified facts live in `.claude/references/`. Still open:

- Password values in child rows of the Single survive a Settings save (SPEC §4.2).
- LangChain/LangGraph wheels and the bench's existing `openai==3.24.0` on Python 3.14.
- `langsmith.Client` input/output hiding parameters (SPEC §11).
- The browser microphone (`getUserMedia`) works only over HTTPS or on `localhost`; `today.localhost` counts as a secure context in Chrome, but production sites need HTTPS.
