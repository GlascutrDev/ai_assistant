# agent

Runs one turn of the assistant: build the agent, stream it, save the transcript, and pause for confirmations.

## Public API

| Name | Purpose |
|---|---|
| `runner.run_turn(conversation, message=None, resume=None)` | Background job (queue `long`). Runs as the enqueuing user. |
| `runner.execute(ctx, graph_input, publisher=None, purpose="agent")` | Stream the graph and collect new messages and interrupts. Reused by `evals/`. |
| `runner.request_cancel(conversation)` | Set the Redis flag that the stream loop checks between events |
| `graph.build(ctx, attachments)` | `create_agent` with the model, tools, system prompt, middleware, and `FrappeCheckpointSaver` |
| `context.TurnContext`, `context.of(runtime)` | Per-turn context; a tool's view of it |
| `prompts.system(ctx, attachments)` | System prompt, including the prompt-injection rules |
| `middleware.token_budget`, `middleware.UsageRecorder` | Budget check before each model call; usage log for every model call |
| `transcript.*` | Graph messages ↔ `AI Message`, totals, title |
| `stream.Publisher` | Realtime events `ai_assistant_stream` to the user's room |

## Turn flow

1. `api.chat.send_message` inserts the user `AI Message`, sets the conversation `Running`, enqueues `run_turn`.
2. `run_turn` checks ownership, builds `TurnContext` (model = `Settings.main_model`), streams the graph with `durability="sync"`.
3. New `AIMessage`/`ToolMessage`s become `AI Message` rows. A `HumanInTheLoop` interrupt becomes one `AI Action Request` per pending write, and the conversation becomes `Waiting for confirmation`.
4. If every write of the interrupt fails its pre-check (`tools/preview.precheck`), the requests are `Failed` and `run_turn` resumes the graph in the same job with reject decisions, so the model can correct the call. After `MAX_AUTO_RESUMES` such passes the turn ends with a system note.
5. `api.chat.decide_action` resumes with `Command(resume={"decisions": [...]})` when every request of the interrupt is decided.

## Invariants

- The graph is the compiled `create_agent` graph. Intake and finalize are runner steps, so their DB writes stay in the job's transaction.
- `execute` calls `dblock.bind_turn()`; every DB call inside the graph runs under `dblock.locked()`.
- User turns use `Settings.main_model` only. `is_evaluation` turns use the target model and log usage as `evaluation`.
- The runner commits once at the end (not in tests).

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_chat
```

`fake_llm.use_models(chat={"fake-main": fake_chat(tool_call(...), "answer", "title")})`. A new conversation uses one extra response for the title.
