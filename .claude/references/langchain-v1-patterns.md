# LangChain v1 / LangGraph / LangSmith patterns

Snippets from the current docs, fetched with Context7 on 2026-10-14 (`/websites/langchain_oss_python_langchain`, `/websites/langchain_oss_python_langgraph`, `/websites/langchain`). For anything not here, query Context7 again and add the snippet. Don't use pre-v1 APIs (`AgentExecutor`, `langgraph.prebuilt.create_react_agent`, `ConversationBufferMemory`).

## Build a model from a Settings row

```python
from langchain.chat_models import init_chat_model

model = init_chat_model(
	row.model_name,
	model_provider=providers.MAP[cred.provider]["model_provider"],  # "anthropic", "openai", "google_genai", ...
	api_key=cred.get_password("api_key"),
	base_url=cred.base_url or providers.MAP[cred.provider]["default_base_url"],  # omit when None
	max_tokens=row.max_output_tokens,
	temperature=row.temperature,
	timeout=row.timeout_seconds,
	max_retries=2,
)
```

OpenAI-compatible providers (Moonshot, OpenRouter, vLLM, Groq): `model_provider="openai"` plus `base_url`. Non-standard response fields from those providers are not kept.

## Agent with tools, context, checkpointer, human-in-the-loop

```python
from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware

@dataclass
class TurnContext:
	user: str
	conversation: str
	model_profile: str
	is_evaluation: bool = False

agent = create_agent(
	model=registry.get_main_model(),
	tools=[*tools.READ_TOOLS, *tools.WRITE_TOOLS],
	system_prompt=prompts.system(ctx),
	context_schema=TurnContext,
	checkpointer=FrappeCheckpointSaver(),
	middleware=[
		attachments_inliner,
		token_budget,
		SummarizationMiddleware(...),   # check its current parameters in Context7 before use
		HumanInTheLoopMiddleware(
			interrupt_on={t.name: {"allowed_decisions": ["approve", "edit", "reject"]} for t in tools.WRITE_TOOLS}
		),
		usage_recorder,
	],
)
config = {"configurable": {"thread_id": conv.name}}
```

Other built-ins seen in the docs: `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`, `ModelFallbackMiddleware`, `PIIMiddleware`, `TodoListMiddleware`. Check parameters in Context7 before use.

## Tools with runtime context

```python
from langchain.tools import tool, ToolRuntime

@tool
def list_documents(doctype: str, filters: dict | None = None, limit: int = 20,
                   runtime: ToolRuntime[TurnContext] = None) -> dict:
	"""List records of a DocType the user can read. Use describe_doctype first for field names."""
	...
```

`runtime.context` is the `TurnContext` passed at invoke time. The `runtime` argument is hidden from the model.

## Middleware hook (model choice, budgets, inlining)

```python
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse

@wrap_model_call
def token_budget(request: ModelRequest, handler) -> ModelResponse:
	budget.assert_available(request.runtime.context.user)
	return handler(request)

# replace the model or messages for this call only:
handler(request.override(model=other_model))
```

## Invoke, stream, interrupt, resume

```python
for chunk in agent.stream(
	{"messages": [user_message]}, config=config, context=ctx,
	stream_mode=["messages", "updates"], version="v2",
):
	if chunk["type"] == "messages":
		token, meta = chunk["data"]          # AIMessageChunk: token.text, token.tool_call_chunks
	elif chunk["type"] == "updates":
		...                                   # node -> state update; "__interrupt__" holds pending writes

from langgraph.types import Command
agent.invoke(
	Command(resume={"decisions": [
		{"type": "approve"},
		{"type": "edit", "edited_action": {"name": "create_document", "args": {...}}},
		{"type": "reject", "message": "Use the other customer."},
	]}),
	config=config, context=ctx, version="v2",
)
```

Interrupt payload: `{"action_requests": [{"name", "arguments", "description"}], "review_configs": [{"action_name", "allowed_decisions"}]}`. Decisions must follow the order of `action_requests`. `result.interrupts` holds them when invoking with `version="v2"`.

## Multimodal input (standard content blocks)

```python
{"role": "user", "content": [
	{"type": "text", "text": question},
	{"type": "image", "base64": b64, "mime_type": "image/png"},
	{"type": "file", "base64": b64, "mime_type": "application/pdf", "extras": {"filename": name}},  # OpenAI needs a filename
	{"type": "audio", "base64": b64, "mime_type": "audio/wav"},
]}
```

Not every model accepts every type. Gate on the `supports_*` flags of the profile.

## Usage

`AIMessage.usage_metadata` → `{"input_tokens", "output_tokens", "total_tokens", "input_token_details": {"cache_read", ...}}`.

## Custom checkpointer

Subclass `langgraph.checkpoint.base.BaseCheckpointSaver`; implement `get_tuple`/`aget_tuple` (by `thread_id`, `checkpoint_ns`, optional `checkpoint_id`), `list`, `put`, `put_writes`, `delete_thread`. `get_tuple` must return the exact checkpoint when `checkpoint_id` is given. Validate:

```python
from langgraph.checkpoint.conformance import checkpointer_test, validate

@checkpointer_test(name="FrappeCheckpointSaver")
async def saver():
	yield FrappeCheckpointSaver()

report = await validate(saver)
assert report.passed_all_base()
```

## LangSmith tracing without environment variables

```python
import langsmith as ls

client = ls.Client(api_key=settings.get_password("langsmith_api_key"), api_url=settings.langsmith_endpoint or None)
with ls.tracing_context(enabled=True, client=client, project_name=project,
                        tags=[site, profile], metadata={"user": user, "conversation": conv}):
	run_graph(...)
```

Check the `tracing_context` `client` argument and input/output hiding options in Context7 before use (SPEC §11.1 [Verify]).

## Evaluation

```python
from langsmith import Client
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

judge = create_llm_as_judge(prompt=CORRECTNESS_PROMPT, judge=registry.get_evaluation_model(), feedback_key="correctness")
# check in Context7 whether create_llm_as_judge takes `judge=<chat model>` or `model="provider:name"` in the installed openevals

def correctness(inputs: dict, outputs: dict, reference_outputs: dict):
	return judge(inputs=inputs, outputs=outputs, reference_outputs=reference_outputs)

results = client.evaluate(
	target, data=settings.evaluation_dataset, evaluators=[correctness, tool_selection, write_confirmed, permission_respected],
	experiment_prefix=target_model, max_concurrency=settings.evaluation_max_concurrency,
	metadata={"target_model": target_model, "evaluation_model": settings.evaluation_model},
)
```

Evaluator signature: any of `inputs`, `outputs`, `reference_outputs` as keyword arguments; return a bool, a number, or `{"key", "score", "comment"}`.
