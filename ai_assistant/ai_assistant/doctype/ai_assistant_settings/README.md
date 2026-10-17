# AI Assistant Settings: প্রতিটি field কী আর কেন

এটি একটি Single DocType, অর্থাৎ পুরো site-এর জন্য একটাই রেকর্ড। Provider, model, key, limit সব এখান থেকেই আসে। Code-এ এগুলোর কোনোটা hard-code করা নেই।

---

## ১. General ট্যাব

| Field | কাজ | কেন দরকার |
|---|---|---|
| **Enabled** | পুরো assistant চালু বা বন্ধ করে | বন্ধ থাকলে কোনো endpoint কাজ করে না। Setup শেষ হওয়ার আগে বন্ধ রাখুন। |
| **Assistant Name** | Chat-এ assistant-এর যে নাম দেখায় (default "AI Assistant") | নিজের brand-এর নাম দিতে চাইলে |
| **Allowed Roles** | এই role-গুলোর user-রাও assistant ব্যবহার করতে পারবে | `AI Assistant User` role ও System Manager এমনিতেই পায়। প্রত্যেক user-কে নতুন role না দিয়ে, যেমন "Sales User", পুরো দলকে access দেওয়া যায়। |
| **Extra Instructions** | System prompt-এর সাথে যোগ হওয়া লেখা | কোম্পানির ভাষা, শব্দ বা নিয়ম শেখানোর জন্য, যেমন "সবসময় BDT-তে টাকা দেখাও" |

## ২. Models ট্যাব

### Providers (child table: AI Provider Credential)
প্রতিটি সারি একটি provider account।

| Field | কাজ |
|---|---|
| **Provider** | Anthropic, OpenAI, Moonshot, Gemini, DeepSeek, Mistral, Ollama, OpenAI Compatible |
| **Label** | এই account-এর একটি অনন্য নাম, যেমন "OpenAI prod"। Model সারি এই নাম দিয়ে account চেনে। |
| **Api Key** | Password field, এনক্রিপ্ট করে রাখা হয়। শুধু `llm/registry.py` এটা পড়ে, browser-এ কখনো যায় না। |
| **Base URL** | ফাঁকা রাখলে provider-এর default URL। OpenAI Compatible (OpenRouter, vLLM, Groq) হলে আবশ্যক। |
| **Organization** | শুধু OpenAI-এর জন্য, ঐচ্ছিক |
| **Enabled** | এই account ব্যবহার হবে কি না |

### Models (child table: AI Model Profile)
প্রতিটি সারি একটি model-এর profile।

| Field | কাজ |
|---|---|
| **Profile ID** | ছোট একটি অনন্য নাম, যেমন `claude-main`। নিচের Model Choice-এ এই নামই বাছাই করা হয়। |
| **Provider Label** | কোন Provider সারির key ব্যবহার হবে |
| **Model Name** | Provider-এর আসল model নাম |
| **Model Type** | Chat / Embedding / Speech-to-text |
| **Max Output Tokens, Context Window** | উত্তর কত বড় হতে পারবে, আর model কতটা context নিতে পারে |
| **Temperature / Use Default Temperature** | উত্তর কতটা সৃজনশীল হবে। কিছু model (Claude Opus 5.5, Sonnet 5.5, Fable) temperature নেয় না, তাদের জন্য "Use Default Temperature" চালু করুন। |
| **Timeout Seconds** | Provider কত সেকেন্ড পর্যন্ত সাড়া না দিলে call বাতিল হবে |
| **Dimensions** | শুধু Embedding model-এর জন্য, vector-এর মাপ |
| **Supports Tools / Images / PDF / Audio** | Model কী কী পারে। Main model-এ **Supports Tools** অবশ্যই চালু থাকতে হবে। Supports PDF চালু থাকলে PDF সরাসরি model-এ যায়, না থাকলে লেখা বের করে পাঠানো হয়। |
| **Input / Output Cost per 1M Tokens, Cost Per Audio Minute** | খরচ হিসাবের জন্য। এগুলো থেকেই AI Usage Log আর মাসিক বাজেট গোনা হয়। |

### Model Choice
| Field | কাজ |
|---|---|
| **Main Model** | প্রতিটি user-এর প্রশ্নের উত্তর এই model দেয় |
| **Test/Evaluation Model** | শুধু evaluation-এ main model-এর উত্তরের নম্বর দেয়, user-কে কখনো উত্তর দেয় না। অন্য provider-এর model হলে ভালো, তাতে model নিজেই নিজের উত্তরে নম্বর দেয় না। |
| **Embedding Model** | RAG (knowledge base) ও বড় file খোঁজার জন্য লেখাকে vector বানায় |
| **Speech Model** | Voice আর audio file থেকে লেখা বানায় |

## ৩. Limits and Safety ট্যাব

| Field | Default | কেন |
|---|---|---|
| **Max Model Calls Per Turn** | 12 | একটি প্রশ্নে model-কে সর্বোচ্চ কতবার call করা যাবে। অসীম loop আর বাড়তি খরচ ঠেকায়। |
| **Max Tool Calls Per Turn** | 20 | একটি প্রশ্নে সর্বোচ্চ কয়টি tool call |
| **Max Rows Per Read** | 100 | এক read-এ সর্বোচ্চ কয়টি রেকর্ড আসবে। Code-এ ৫০০-র hard cap আছে। |
| **Max Tool Result Chars** | 12000 | Tool-এর ফলাফল এর বেশি লম্বা হলে কেটে ছোট করা হয়, যাতে context ভরে না যায় |
| **Summarize After Tokens** | 60000 | কথোপকথন এর চেয়ে বড় হলে পুরোনো অংশের সারাংশ বানানো হয় |
| **User Daily Token Limit** | 200000 | একজন user দিনে কত token খরচ করতে পারবে (0 = সীমা নেই) |
| **Site Monthly Cost Limit** | 0 | পুরো site-এর মাসিক খরচের সীমা (0 = সীমা নেই) |
| **Read Only Mode** | বন্ধ | চালু করলে সব write tool সরিয়ে দেওয়া হয়, assistant কিছুই বদলাতে পারে না |
| **Action Request TTL (Minutes)** | 60 | Approve/Reject-এর অপেক্ষায় থাকা কোনো পরিবর্তন এত মিনিট পর Expired হয়ে যায় |
| **Blocked DocTypes** | — | প্রতি লাইনে একটি DocType, যেটা assistant কখনো পড়বে না বা লিখবে না (যেমন Salary Slip)। AI DocType-গুলো সবসময়ই blocked থাকে। |

## ৪. Knowledge ট্যাব (RAG)

| Field | কাজ |
|---|---|
| **RAG Enabled** | Knowledge base-এ খোঁজা (`search_knowledge`) চালু করে |
| **Index Stale** | এটা system নিজে চালু করে, আপনি নয়। Embedding model বদলালে চালু হয়, আর index rebuild না হওয়া পর্যন্ত search বন্ধ থাকে, কারণ পুরোনো আর নতুন vector মেলে না। |
| **Knowledge Sources** | কোন DocType-এর রেকর্ড index হবে। প্রতি সারিতে থাকে **Source Doctype**, **Content Fields** (কোন field-এর লেখা; ফাঁকা রাখলে সব text field), **Filters (JSON)** (যেমন `{"docstatus": 1}`), আর **Enabled**। |
| **Chunk Size** (1200) | লেখাকে কত অক্ষরের টুকরোয় ভাগ করা হবে |
| **Chunk Overlap** (150) | পাশাপাশি দুই টুকরোয় কতটা লেখা মিলবে, যাতে বাক্য মাঝখানে কেটে অর্থ না হারায় |
| **Top K** (6) | একবার খুঁজলে কয়টি সবচেয়ে কাছের টুকরো ফেরত আসবে |

## ৫. Voice and Files ট্যাব

| Field | কাজ |
|---|---|
| **Voice Enabled** | Microphone button দেখায় |
| **Max Voice Seconds** (120) | সর্বোচ্চ কত সেকেন্ড রেকর্ড করা যাবে |
| **Voice Auto Send** | চালু থাকলে transcript সাথে সাথে পাঠানো হয়। বন্ধ থাকলে (default) user আগে লেখাটা দেখে ঠিক করে তারপর Send করেন। |
| **Attachments Enabled** | Paperclip, drag-drop আর paste চালু করে |
| **Allowed File Types** | কোন extension অনুমোদিত। তবে file-এর আসল ধরন content দেখেই যাচাই হয়, নাম বদলে ফাঁকি দেওয়া যায় না। |
| **Max File Size (MB)** (20) | একটি file-এর সর্বোচ্চ আকার |
| **Max Files Per Message** (5) | এক message-এ সর্বোচ্চ কয়টি file |
| **Max Attachment Text Chars** (30000) | এর চেয়ে লম্বা লেখা পুরোটা model-এ পাঠানো হয় না। টুকরো করে index হয় আর `search_attachments` দিয়ে খোঁজা হয়। |

## ৬. LangSmith ট্যাব

| Field | কাজ |
|---|---|
| **LangSmith Enabled** | প্রতিটি turn LangSmith-এ trace হবে কি না (debug আর মান যাচাইয়ের জন্য) |
| **LangSmith API Key** | এনক্রিপ্ট করে রাখা হয়। Environment variable থেকে নয়, এখান থেকে নেওয়া হয়, তাই একই bench-এর আলাদা site-এর আলাদা key থাকতে পারে। |
| **LangSmith Project** | ফাঁকা রাখলে `ai_assistant-<site>` |
| **LangSmith Endpoint** | ফাঁকা রাখলে LangSmith SaaS। Self-hosted হলে এখানে তার URL দিন। |
| **Hide Inputs and Outputs** (চালু) | Trace-এ message-এর আসল লেখা যায় না, শুধু structure যায়। ব্যবসার ডেটা বাইরে যাওয়া ঠেকায়। |

### Evaluation section
| Field | কাজ |
|---|---|
| **Evaluation Dataset** | LangSmith-এ test প্রশ্নগুলোর dataset-এর নাম |
| **Evaluation User** | Evaluation-এর সময় agent কোন user হিসেবে চলবে। Administrator বা System Manager দেওয়া যাবে না, যাতে permission পরীক্ষাটা আসল হয়। |
| **Min Correctness** (80%) · **Min Groundedness** (90%) | Pass mark। এর কম পেলে নতুন model-কে Main Model বানানো উচিত নয়। |
| **Evaluation Max Concurrency** (2) | কয়টি test প্রশ্ন একসাথে চলবে |

### Retention section
| Field | কাজ |
|---|---|
| **Conversation Retention Days** (180) | এত দিনের পুরোনো কথোপকথন, তার message আর attachment, প্রতিদিনের job মুছে ফেলে (0 = চিরকাল রাখা হয়) |

---

**ন্যূনতম setup-এর ক্রম:**
1. একটি Provider যোগ করুন।
2. অন্তত একটি Chat model profile যোগ করুন, তাতে Supports Tools চালু রাখুন।
3. সেটিকে Main Model হিসেবে বেছে নিন।
4. **Actions → Test Connection** চালান।
5. **Enabled** চালু করুন।

Knowledge, Voice, Files আর LangSmith ঐচ্ছিক। দরকার হলে পরে চালু করবেন।

---


## Index Stale কখন চালু হয়

এটা চালু হয় [ai_assistant_settings.py:113-122](ai_assistant/doctype/ai_assistant_settings/ai_assistant_settings.py#L113-L122)-এ। Settings save করার সময় `validate()` আগের আর নতুন embedding model তুলনা করে। নিচের তিনটার যেকোনো একটা বদলালে `index_stale = 1` হয়:

- **Embedding Model** (profile ID)
- সেই profile-এর **Model Name**
- সেই profile-এর **Dimensions**

**কেন:** পুরোনো model-এর vector আর নতুন model-এর vector একই "ভাষা"য় থাকে না, মাপও আলাদা হতে পারে। তাই নতুন model দিয়ে পুরোনো index-এ খুঁজলে ভুল ফল আসবে বা query fail করবে।

**চালু থাকলে যা হয়:**
- [rag/indexer.py:115](rag/indexer.py#L115) `is_searchable()` False ফেরত দেয়, তাই knowledge search বন্ধ থাকে।
- [rag/indexer.py:62](rag/indexer.py#L62) `sync()` কিছু করে না, ফলে রেকর্ড বদলালেও নতুন indexing হয় না।
- Form-এ কমলা রঙের সতর্কবার্তা দেখায় ([ai_assistant_settings.js:17](ai_assistant/doctype/ai_assistant_settings/ai_assistant_settings.js#L17))।

**কীভাবে বন্ধ হয়:** **Actions → Rebuild Knowledge Index** চাপলে [rag/indexer.py:87](rag/indexer.py#L87) `rebuild_all()` চলে। এটা নতুন dimensions দিয়ে table আবার বানায়, flag 0 করে, তারপর সব source আবার index করে।

## কোন field code-এর কোথায় পড়া হয়

| Field | যেখানে ব্যবহার হয় |
|---|---|
| enabled | [services/access.py](services/access.py), [api/chat.py](api/chat.py) |
| assistant_name, extra_instructions | [agent/prompts.py](agent/prompts.py) (system prompt) |
| allowed_roles | [services/access.py](services/access.py) |
| main_model, evaluation_model, embedding_model | [llm/registry.py](llm/registry.py) |
| speech_model | [llm/speech.py](llm/speech.py) |
| max_model_calls_per_turn, max_tool_calls_per_turn, summarize_after_tokens | [agent/graph.py](agent/graph.py) (middleware) |
| max_rows_per_read, blocked_doctypes | [services/settings.py](services/settings.py) |
| max_tool_result_chars | [tools/serialize.py](tools/serialize.py) |
| user_daily_token_limit, site_monthly_cost_limit | [services/budget.py](services/budget.py) |
| read_only_mode | [tools/guard.py](tools/guard.py), [tools/\_\_init\_\_.py](tools/__init__.py), [agent/graph.py](agent/graph.py) |
| action_request_ttl_minutes | [services/actions.py](services/actions.py) (hourly expire) |
| rag_enabled, knowledge_sources, chunk_size, chunk_overlap | [rag/indexer.py](rag/indexer.py) |
| top_k | [tools/knowledge.py](tools/knowledge.py), [tools/files.py](tools/files.py) |
| voice_enabled, max_voice_seconds | [services/voice.py](services/voice.py), [public/js/chat/voice.js](public/js/chat/voice.js) |
| voice_auto_send | শুধু browser-এ: [public/js/chat/voice.js](public/js/chat/voice.js) |
| attachments_enabled, allowed_file_types, max_file_size_mb, max_files_per_message | [attachments/upload.py](attachments/upload.py), [services/attachments.py](services/attachments.py), [public/js/chat/files.js](public/js/chat/files.js) |
| max_attachment_text_chars | [attachments/processor.py](attachments/processor.py) |
| langsmith_* (5টি) | [observability/tracing.py](observability/tracing.py) |
| evaluation_dataset, evaluation_user, min_correctness, min_groundedness | [evals/runner.py](evals/runner.py) |
| conversation_retention_days | [services/attachments.py:151](services/attachments.py#L151) `purge_old()` (daily job) |

UI-তে দেখানোর জন্য বেশিরভাগ field [services/bootstrap.py](services/bootstrap.py) হয়ে browser-এ যায়।

## একটা সমস্যা: Evaluation Max Concurrency কোথাও ব্যবহার হয় না

**Evaluation Max Concurrency** field-টা কোনো code পড়ে না। [evals/runner.py:91](evals/runner.py#L91)-এ মান hard-code করা আছে: `max_concurrency=0`। ফলে test প্রশ্নগুলো সবসময় একটার পর একটা চলে, field-এ default 2 বা অন্য যা-ই লেখা থাকুক।

এটা সম্ভবত ইচ্ছাকৃত। Graph-এর সব কাজ job-এর একই DB connection ভাগ করে চালায় (CLAUDE.md gotcha দেখুন), তাই একসাথে একাধিক প্রশ্ন চালানো নিরাপদ নাও হতে পারে। তবে এখন field-টা ভুল ধারণা দেয়। দুটো পথ আছে:

1. **Field মুছে ফেলা** (আমার সুপারিশ), কারণ sequential চালানোই নিরাপদ।
2. Field-টা পড়ার ব্যবস্থা করা, এবং তার আগে যাচাই করা যে concurrency > 0 হলে `dblock` ঠিকমতো কাজ করে।

কোনটা করব জানালে সেটা করে দেব।

`doctype/ai_assistant_settings/README.md` file-টা Bengali লেখা দিয়ে শুরু হয়েছে। আমার আগের উত্তর সেখানে রাখার জন্য file-টা বানিয়ে থাকলে খেয়াল রাখবেন: আপনার নিয়ম অনুযায়ী module README developer আর agent-দের জন্য। এ ধরনের field ব্যাখ্যা root README বা আলাদা user guide-এ রাখাই বেশি মানানসই।