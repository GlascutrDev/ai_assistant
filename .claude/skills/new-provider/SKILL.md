---
name: new-provider
description: Add an LLM, embedding, or speech-to-text provider (or a model capability) to ai_assistant so admins can select it in AI Assistant Settings. Use when asked to support a new provider or model family such as Groq, xAI, Bedrock, Azure, or a local server.
---

# New provider

1. **Check the docs first** with Context7 (`resolve-library-id` → `query-docs`): the `init_chat_model` provider string, the `langchain-<provider>` package, embedding support, and speech-to-text support. If the provider has an OpenAI-compatible endpoint, prefer `OpenAI Compatible` + `base_url` over a new package.
2. **Settings:** add the option to `AI Provider Credential.provider` (SPEC §4.2). Migrate both sites.
3. **Mapping** in `ai_assistant/llm/providers.py`, one entry:
   `{"model_provider": ..., "default_base_url": ..., "chat": True, "embeddings": bool, "speech": bool, "needs_api_key": bool}`.
   `llm/registry.py` builds every model from this map; don't add provider branches elsewhere.
4. **Package:** add `langchain-<provider>` to `pyproject.toml` only if needed. Ask the user before `bench setup requirements --python`, because it changes the shared bench env. Check it installs on Python 3.14 and does not change the bench's `openai` pin.
5. **Speech:** if `speech: True`, add the branch in `llm/speech.py` (SPEC §6.7).
6. **Tests** in `ai_assistant/tests/test_llm_registry.py`: the registry builds the right class with key, `base_url`, `max_tokens`, `temperature`, `timeout` from a Settings row. Patch the network; never call the provider.
7. **Manual check:** ask the user to press **Test connection** on the provider row and report the result. You don't hold their keys.
8. **Docs:** SPEC §6.2 table (and §6.7 for speech), README provider table for admins, `ai_assistant/llm/README.md`.
