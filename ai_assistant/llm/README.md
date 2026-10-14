# llm

Builds chat, embedding, and speech models from `AI Assistant Settings`, and records their usage.

## Public API

| Function | Purpose |
|---|---|
| `registry.get_main_model()` | Chat model for every user turn (`Settings.main_model`) |
| `registry.get_evaluation_model()` | Test/evaluation model. Call only from `evals/`. |
| `registry.get_chat_model(profile_id)` | Any enabled Chat profile (a candidate in an evaluation run) |
| `registry.get_embeddings()` | Embedding model (`Settings.embedding_model`) |
| `registry.resolve(profile_id, model_type)` | `(profile row, credential row)`; raises `ModelNotConfiguredError` |
| `registry.redact(text, credential)` | Remove the key from an error message |
| `providers.PROVIDERS` | Provider → LangChain `model_provider`, default `base_url`, embedding and speech support |
| `usage.record(...)` | Insert `AI Usage Log` with cost, and invalidate the budget totals |
| `connection.test(label)` | One small call for the **Test Connection** button |
| `speech.transcribe(...)` | Speech-to-text (voice prompts, audio files) |

## Invariants

- API keys are read with `get_password` only in `registry.py` and `speech.py`. Never return, log, or store them.
- Models are cached per site, profile, and `Settings.modified`. A Settings save takes effect on the next call.
- No hard-coded model names here. Defaults live in `install.py`.

## How to test

`tests/fake_llm.use_models(chat={profile_id: fake_chat(...)}, embeddings=FakeEmbeddings())` patches `_build_chat` and `_build_embeddings`. No test calls a real provider.

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_registry
```
