---
name: attachment-type
description: Add or change a chat attachment type or the voice pipeline in ai_assistant — upload checks, content sniffing, extractor, delivery (native, text, indexed), and tests. Use when asked to support a new file format, change how files reach the model, or change voice recording/transcription.
---

# Attachment type or voice change

1. **Read** SPEC §6.7 (voice), §6.8 (attachments), §7.3–§7.4 (safety), CLAUDE.md rules 16–18, and `.claude/references/multimodal-and-files.md`.
2. **Upload checks** in `ai_assistant/attachments/upload.py`:
   - add the extension to the `allowed_file_types` default (Settings, SPEC §4.1) and the extension → MIME map
   - the sniffed MIME type (`filetype`) must match the extension; text formats are checked by UTF-8 decode
   - zip-based formats: reject when the unpacked size exceeds 100 MB
3. **Extractor** in `attachments/extractors.py`: a pure function `bytes -> Extracted(text, page_count, meta)`. No network, no macros, no shell tools.
4. **Delivery** in `attachments/processor.py`: `kind`, and `native` only when the main model has the matching `supports_*` flag; otherwise `text`, or `indexed` above `max_attachment_text_chars`.
5. **Never put bytes in graph state.** The message keeps `AI Attachment` names; `agent/middleware.py` `attachments_inliner` builds the LangChain v1 content blocks for the model request only.
6. **Voice:** recorder code lives in `public/js/chat/voice.js` (MediaRecorder, mime type fallback, silence stop, `max_voice_seconds`). Server side is `api.chat.transcribe` → `llm/speech.py`. The transcript goes to the input box, not straight to the agent, unless `voice_auto_send`.
7. **Tests** in `ai_assistant/tests/test_attachments.py` with small fixture files in `tests/fixtures/`:
   - valid file → `Ready` with the expected `delivery`
   - the same bytes renamed to a wrong extension → refused, no `File` created
   - oversize → refused
   - user B cannot use user A's attachment
   - for native delivery: the fake LLM receives the content block; the checkpoint has no bytes
8. **Run** `bench --site today-test.localhost run-tests --module ai_assistant.tests.test_attachments` and report the real output.
9. **Docs:** SPEC §6.8 table, Settings default in SPEC §4.1, README "What files can I attach", `ai_assistant/attachments/README.md`.
