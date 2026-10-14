# Voice and file attachments

SPEC §6.7–6.8. Checked on 2026-10-14.

## Speech-to-text (OpenAI SDK in the bench: `openai` 3.24.0)

```python
from openai import OpenAI

client = OpenAI(api_key=cred.get_password("api_key"), base_url=cred.base_url or None, timeout=row.timeout_seconds)
result = client.audio.transcriptions.create(
	file=(file_name, audio_bytes, mime_type),
	model=row.model_name,          # e.g. gpt-4o-transcribe, whisper-1, or a Groq/self-hosted Whisper name
	language=lang_hint,            # ISO-639-1 from the user's Frappe language; omit if unknown
)
text = result.text
```

Verified signature (keyword-only): `create(*, file, model, chunking_strategy, include, keywords, known_speaker_names, known_speaker_references, language, prompt, response_format, …)`.

- Accepted formats (OpenAI): flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm. Browsers record `webm` (Chrome, Firefox) or `mp4` (Safari), so no conversion is needed.
- Gemini: no transcription endpoint; send an `audio` content block to the Gemini chat model with a fixed "Transcribe verbatim. Output only the transcript." instruction.
- Log `audio_seconds` from the upload (measure with the browser's recording timer, re-checked server side from the file when possible).

## Browser recording (secure context only)

```js
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/mp4";
const rec = new MediaRecorder(stream, { mimeType: type });
```

- Works on HTTPS and on `localhost`/`*.localhost` in Chrome. Production needs HTTPS.
- Stop all tracks after recording (`stream.getTracks().forEach(t => t.stop())`) so the browser mic indicator turns off.
- Silence stop: an `AnalyserNode` on the stream; stop after 3 s below a threshold.

## Upload checks (server)

| Check | How |
|---|---|
| Extension allowed | `allowed_file_types` in Settings |
| Real type | `filetype.guess(bytes)` must match the extension's MIME; text types: strict UTF-8 decode |
| Size | `len(bytes) <= max_file_size_mb * 1024 * 1024` before saving |
| Zip bombs (docx, xlsx) | sum of `ZipInfo.file_size` ≤ 100 MB before parsing |
| Images | Pillow: open, `ImageOps.exif_transpose`, `thumbnail((2048, 2048))`, save without EXIF |
| Storage | private `File` attached to the `AI Conversation` |

## Extraction

| Kind | Library | Notes |
|---|---|---|
| pdf | `pypdf.PdfReader(BytesIO(b))`, `page.extract_text()` | scanned PDFs give no text: deliver native only if the model `supports_pdf` |
| docx | `docx.Document(BytesIO(b))` | paragraphs, then tables as Markdown |
| xlsx | `openpyxl.load_workbook(BytesIO(b), read_only=True, data_only=True)` | per sheet: header + rows as a Markdown table; cap rows |
| csv | `csv.reader(io.StringIO(text))` | sniff dialect |
| txt, md, json | UTF-8 decode | |
| audio | speech model | transcript |

Extracted text is untrusted. Wrap it for the model:

```
<attachment name="bill.pdf" kind="pdf" pages="2">
...text...
</attachment>
```

## Content blocks to the model
See `langchain-v1-patterns.md` "Multimodal input". Build them in `attachments_inliner` from `AI Attachment` names, per model call; don't store base64 in graph state or `AI Message`.
