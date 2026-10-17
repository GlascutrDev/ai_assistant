# evals

Runs the real graph against a LangSmith dataset to grade the main model or a candidate model (SPEC §11.2). Test site only.

## Public API

| Name | Purpose |
|---|---|
| `runner.run(evaluation_run=None, target_model=None)` | Run an evaluation; writes an `AI Evaluation Run` |
| `runner.assert_allowed()` | Raises `EvaluationRefusedError` unless `allow_tests` is on, LangSmith is on, `evaluation_user` is set and is not a System Manager, and `evaluation_model` is set |
| `runner.passed(scores)` | Compare scores with the pass marks in Settings |
| `dataset.load()` / `dataset.ensure(client, name)` | Read `dataset.json`; create or update the LangSmith dataset |
| `fixtures.ensure(user)` | Create the ToDo and Note records the examples refer to |
| `evaluators.Evaluators` | Safety checks (`tool_selection`, `write_confirmed`, `permission_respected`), `cost`, and the LLM-as-judge groundedness check |

## Invariants

- Runs only where `allow_tests` is on, as `evaluation_user`.
- Every write interrupt is rejected (`REJECTION`). Nothing is written.
- The judge uses `get_evaluation_model()` only. This package is the only caller of it.
- Deterministic evaluators come first; add an LLM judge only when a rule cannot decide.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_evals
```

A real run (LangSmith on): `bench --site today-test.localhost execute ai_assistant.evals.runner.run`.
