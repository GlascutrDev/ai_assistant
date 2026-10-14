---
name: eval-case
description: Add evaluation examples or evaluators to ai_assistant/evals and run a LangSmith evaluation of the main model or a candidate model, graded by the test/evaluation model. Use when asked to evaluate, benchmark, compare models, add a regression case, or decide whether to switch the main model.
---

# Evaluation cases and runs

1. **Read** SPEC §11.2, CLAUDE.md rules 8 and 15, and `.claude/references/langchain-v1-patterns.md` ("Evaluation").
2. **Add an example** to `ai_assistant/evals/dataset.json`:
   ```json
   {"inputs": {"question": "How many open ToDos are assigned to me?"},
    "outputs": {"answer": "3 open ToDos", "expected_tools": ["count_documents"],
                "expect_write": null, "must_refuse": false}}
   ```
   - Data the example needs goes in `evals/fixtures.py` (idempotent; run as `evaluation_user`'s data on the test site).
   - Every new tool gets at least one example. Every bug found in chat gets a regression example.
   - Add safety examples too: a blocked DocType, a document the evaluation user cannot read, and a prompt-injection document.
3. **New evaluator** in `evals/evaluators.py`:
   - deterministic when possible (tool names, interrupts, audit rows)
   - LLM-as-judge only with `get_evaluation_model()`; never `get_main_model()` and never a hard-coded model
   - return `{"key": ..., "score": 0..1, "comment": ...}`
4. **Push the dataset:** `bench --site today-test.localhost execute ai_assistant.evals.dataset.push`.
5. **Run** (needs LangSmith on and `allow_tests` on the site):
   `bench --site today-test.localhost execute ai_assistant.evals.runner.run --kwargs "{'target_model': '<profile_id>'}"`
   Omit `target_model` to evaluate the current main model. Real provider calls cost money: tell the user the example count and models before you start, and ask first.
6. **Report:** the `AI Evaluation Run` scores against the thresholds, pass/fail, the LangSmith experiment URL, and for a candidate the comparison with the main model's last passed run. Don't change `main_model` yourself; recommend it.
7. **Unit tests** for evaluators use fake models: `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_evals`.
