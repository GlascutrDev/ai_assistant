---
name: acceptance-test
description: Write or run the SPEC §14 acceptance tests (AC01–AC41) for ai_assistant and report coverage. Use when asked about acceptance criteria, release readiness, or "do we meet the spec".
---

# Acceptance tests

1. Read SPEC §14. Each AC maps to exactly one test method `test_acNN_<short_name>` in `ai_assistant/tests/test_acceptance_<area>.py` (`access`, `tools`, `actions`, `models`, `rag`, `evals`, `attachments`, `voice`).
2. **No real providers.** Use `tests/fake_llm.py`: a `GenericFakeChatModel`-style model that returns scripted `AIMessage`s with `tool_calls`, and fake embeddings / speech. Patch `llm.registry` to return them.
3. Build data with `tests/factories.py`: users with and without the `AI Assistant User` role, user permissions, `ToDo`/`Note`/`Contact` records, Settings rows. Never depend on site data. ERPNext is not on the test site.
4. Act as real users with `with self.set_user(...)` and go through `ai_assistant.api.*` or `agent.runner.run_turn` with jobs run inline, so permissions are covered.
5. Assert on database state: `AI Action Request` status, `AI Audit Log` outcomes, `AI Usage Log` rows, created documents and their `owner`, `File.is_private`, checkpoint contents.
6. Run from `/home/nazmul/Desktop/AROMA`: `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_acceptance_<area>`. Never the dev site.
7. Report a table: AC# → test → PASS / FAIL / MISSING, with failure excerpts. A skipped test is MISSING, not PASS.
