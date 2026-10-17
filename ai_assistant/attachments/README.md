# attachments

Checks uploaded chat files, extracts their text, and chooses how the model gets them (SPEC §6.8). The lifecycle (create, enqueue, purge) is in `services/attachments.py`.

## Public API

| Function | Purpose |
|---|---|
| `upload.check(file_name, data, voice=False)` | Allow-list, content sniffing, size. Returns `CheckedFile`; raises `UploadRefusedError` |
| `upload.clean_image(data, mime)` | Rotate by EXIF, scale to `MAX_IMAGE_SIDE`, save without EXIF |
| `extractors.extract(kind, data, file_name)` | Text and page count per kind (pdf, docx, xlsx, csv, text) |
| `processor.process(kind, data, file_name, mime_type, conversation)` | Returns `Processed` with delivery `native`, `text`, or `indexed` |
| `processor.display_text(text)` | Text cut to `DISPLAY_CHARS` for the UI |

## Invariants

- The type comes from the bytes, not the extension. A renamed file is refused.
- Office files are parsed as zip/XML only. `check_zip` limits the unzipped size (`MAX_UNZIPPED`).
- Images go `native`. PDFs go `native` only if the main model has `supports_pdf` and the file has at most `MAX_NATIVE_PDF_PAGES` pages. Text longer than `max_attachment_text_chars` goes `indexed`.
- Audio is transcribed with `llm.speech`; the model receives the transcript only.
- Nothing here puts bytes in graph state (CLAUDE.md rule 17).

## How to test

```
bench --site today-test.localhost run-tests --module ai_assistant.tests.test_attachments
```
