# observability

LangSmith tracing configured from `AI Assistant Settings`, per site (SPEC §11.1).

## Public API

| Function | Purpose |
|---|---|
| `tracing.tracer(ctx, purpose="agent")` | `LangChainTracer` for one turn, or `None` when tracing is off or the turn is an evaluation |
| `tracing.get_client()` | LangSmith `Client` from Settings, or `None` |
| `tracing.project_name()` | LangSmith project for this site |
| `tracing.root_run_id(tracer)` | Run id to store on the turn |
| `tracing.flush(tracer)` | Send pending runs before the job ends |

## Invariants

- Configuration comes from Settings, never from environment variables. Sites on one bench do not share a project or key.
- Metadata holds user, conversation, and model profile only. Never API keys (CLAUDE.md rule 7).
- Evaluations are traced by `Client.evaluate`, not by this tracer.

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_tracing
```
