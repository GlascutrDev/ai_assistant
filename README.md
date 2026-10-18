## AI Assistant

A chat assistant in Frappe/ERPNext Desk that works **as the signed-in user**. It can see and do only what that user can see and do in Desk.

With the assistant you can:

- ask about your data: lists, counts, totals, reports, and single records
- ask "how do I…" questions about your company's knowledge base
- prepare changes (create, update, submit, cancel, delete, comment, assign, workflow actions, attach files). **Every change waits for your approval.**
- attach files (images, PDF, Word, Excel, CSV, text, audio) and ask about them
- speak your question instead of typing it

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench setup requirements --python
bench --site <your-site> install-app ai_assistant
bench build --app ai_assistant
```

### Set up (System Manager)

Open **AI Assistant Settings**.

1. **Providers** (Models tab): add one row per provider account. Enter the API key and turn on **Enabled**.

   | Provider | Notes |
   |---|---|
   | Anthropic | Claude models |
   | OpenAI | Chat, embedding, and speech-to-text models |
   | Moonshot | Kimi models |
   | Google Gemini | Chat, embedding, and speech-to-text |
   | DeepSeek | Chat models |
   | Mistral | Chat and embedding models |
   | Ollama | Local models. No API key. Base URL defaults to `http://localhost:11434`. |
   | OpenAI Compatible | OpenRouter, vLLM, LiteLLM, Azure OpenAI, Groq, a self-hosted Whisper server. Base URL is required. |

2. **Models**: add one row per model you want to use. Give each a short **Profile ID**, its provider label, the model name, the type (Chat, Embedding, or Speech-to-text), token limits, and prices. Turn on **Enabled**. A chat model that the assistant uses must have **Supports Tools** on.
3. **Model Choice**: pick the **Main Model** (answers users) and the **Test/Evaluation Model** (grades the main model in evaluation runs). Use a different provider for the evaluation model if you can. Pick an **Embedding Model** for the knowledge base and large files, and a **Speech Model** for voice.
4. Use **Actions → Test Connection** to check each provider.
5. **General**: turn on **Enabled**. Users with the role **AI Assistant User**, System Managers, and users with a role in **Allowed Roles** can use the assistant.

Other settings:

| Tab | What you set |
|---|---|
| Limits and Safety | Model and tool calls per answer, rows per read, daily tokens per user, monthly cost per site, read-only mode, record types the assistant may never touch, how long an approval stays open |
| Knowledge | Turn on the knowledge base, choose record types to index, chunk size, results per search. Add articles in **AI Knowledge Document**. After you change the embedding model, use **Actions → Rebuild Knowledge Index**. |
| Voice and Files | Turn voice and attachments on, file types, size limits, recording length, send the transcript at once or let the user check it first |
| LangSmith | Tracing to LangSmith (optionally without message content), the evaluation dataset and user, pass marks |
| Retention | How many days to keep conversations (0 = keep) |

### Using the assistant

- Open **AI Assistant** from the apps screen to reach the **AI Hub** workspace: chat, conversations, knowledge documents, usage, and settings in one place.
- Click the round button at the bottom right of any Desk page, or press **Ctrl+I**. Open the full page at **/desk/ai-assistant** for a larger view and your conversation list.
- When a form is open, the assistant knows which record you mean by "this".
- Answers link to the records they mention.
- **Files:** click the paperclip, drag files onto the chat, or paste an image. Wait until each file shows as ready, then send.
- **Voice:** click the microphone and speak. Recording stops after 3 seconds of silence, when you click again, or at the time limit. Check the text, then press **Send**.
- **Stop** ends an answer that is still running.

### Approving changes

The assistant never changes data on its own. It shows a card with the change and the exact values:

- **Approve** runs the change as you. Your name shows as the owner or modifier, and the record's timeline notes that the AI Assistant did it for you.
- **Edit** lets you correct the values before it runs.
- **Reject** cancels it. You can say why, and the assistant will adjust.

If you lost the permission in the meantime, the change fails and nothing is written. Open approvals expire after the time set in Settings.

### Usage and logs (System Manager)

- **AI Usage Summary** report: tokens and cost by user, model, day, or purpose.
- **AI Audit Log**: every action the assistant tried, with its outcome. It holds no document content.
- **AI Evaluation Run**: results of **Actions → Run Evaluation**, which tests the main model or a candidate model on a test site before you switch to it.

### Troubleshooting

**"Live streaming is not connected … (xhr poll error)"**: the browser cannot reach Frappe's socket.io server. Chat still works, but each reply appears only when it is complete. On the server:

1. Make sure socket.io is running. In development, the bench `Procfile` needs `socketio: bench socketio` and `bench start` must be running. In production, `sudo supervisorctl status` must show the `node-socketio` process as RUNNING. If it does not, run `bench setup supervisor`, then `sudo supervisorctl reread && sudo supervisorctl update`.
2. Check that it answers: `curl -s "http://localhost:9000/socket.io/?EIO=4&transport=polling"` should return text starting with `0{"sid"`. The port is `socketio_port` in `sites/common_site_config.json`.
3. Make sure the browser can reach it. In development, opened from another computer: open port 9000 in the firewall as well as 8000. In production: run `bench setup nginx && sudo nginx -t && sudo systemctl reload nginx` so nginx proxies `/socket.io`. Open the site through nginx, not on `:8000`.
4. Make sure the Redis servers in `common_site_config.json` (`redis_socketio`, `redis_queue`) are running.
5. Run `bench build --app ai_assistant`, then hard-refresh the browser.

If the message changes to **Invalid namespace** or **Invalid origin**, open the site by its site name rather than its IP address.

**"… (Unauthorized: TypeError: fetch failed)"**: the browser reaches socket.io, but the server cannot reach the site at the address the browser used. To check the user's login, socket.io calls the site at that address. Test it on the server, from the bench folder:

```bash
node -e 'fetch(process.argv[1]+"/api/method/ping").then(r=>r.text()).then(console.log).catch(e=>console.error(e.cause))' "http://<address you open in the browser>"
```

- `ENOTFOUND` or `ETIMEDOUT`: on the server, add `127.0.0.1  <site host name>` to `/etc/hosts`.
- `ECONNREFUSED` (development): set the right `webserver_port` in `sites/common_site_config.json`, and make sure `bench start` is running.
- Certificate error (self-signed HTTPS): set `NODE_EXTRA_CA_CERTS=/path/to/ca.pem` for the socketio process in `config/supervisor.conf`, or use a trusted certificate (`bench setup lets-encrypt`).

When the command prints `pong`, restart bench and refresh the browser.

### Contributing

This app uses `pre-commit` (ruff, eslint, prettier):

```bash
cd apps/ai_assistant
pre-commit install
```

### License

MIT
