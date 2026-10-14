#!/usr/bin/env bash
# PostToolUse(Write|Edit): flag likely CLAUDE.md rule violations back to Claude (non-blocking).
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
[ -f "$f" ] || exit 0
rel=${f#"$CLAUDE_PROJECT_DIR"/}
issues=()

hit() { grep -nE "$1" "$f" | grep -v '^\s*[0-9]*:\s*#' | head -3 | sed 's/^/    /'; }

case "$rel" in
	ai_assistant/*.py)
		[[ "$rel" == */tests/* ]] && is_test=1 || is_test=0

		case "$rel" in
			ai_assistant/tools/* | ai_assistant/api/* | ai_assistant/attachments/* | ai_assistant/agent/*)
				m=$(hit 'ignore_permissions\s*=\s*True|flags\.ignore_permissions|frappe\.set_user\(|frappe\.get_all\(|frappe\.db\.(get_all|get_value|get_values|count|exists|sql|set_value)\(|\.db_set\(|\beval\(|\bexec\(|safe_exec|frappe\.get_attr\(')
				[ -n "$m" ] && issues+=("Rule 1: permission-bypassing or unsafe call in code the agent can reach (see .claude/references/permission-safe-tools.md):\n$m")
				;;
		esac

		if [[ "$rel" == ai_assistant/tools/* ]]; then
			m=$(hit '\.get_password\(')
			[ -n "$m" ] && issues+=("Rule 7: tools must never read Password fields:\n$m")
		fi

		[[ $is_test == 1 || "$rel" == ai_assistant/install.py ]] || {
			m=$(hit '["'"'"'](claude-[a-z0-9.-]+|gpt-[0-9a-z.-]+|kimi-[a-z0-9.-]+|gemini-[0-9a-z.-]+|text-embedding-[a-z0-9-]+|whisper-1|gpt-4o-transcribe)["'"'"']')
			[ -n "$m" ] && issues+=("Rule 8: hard-coded model name; read it from AI Assistant Settings via llm/registry.py:\n$m")
			m=$(hit '(sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|lsv2_[A-Za-z0-9_]{16,})')
			[ -n "$m" ] && issues+=("Rule 7: something that looks like an API key is in source:\n$m")
		}

		if [[ "$rel" != ai_assistant/evals/* && $is_test == 0 ]]; then
			m=$(hit 'get_evaluation_model\(')
			[ -n "$m" ] && issues+=("Rule 8: the test/evaluation model is used only in ai_assistant/evals/:\n$m")
		fi

		m=$(hit '^\s*(from|import)\s+(erpnext|hrms|crm|frappe_whatsapp)\b')
		[ -n "$m" ] && issues+=("Rule 13: no imports from other bench apps (required_apps = []):\n$m")

		m=$(hit 'AgentExecutor|create_react_agent|ConversationBufferMemory|initialize_agent')
		[ -n "$m" ] && issues+=("LangChain v1 only (create_agent + middleware); see .claude/references/langchain-v1-patterns.md:\n$m")

		if [[ "$rel" == ai_assistant/api/*.py ]]; then
			m=$(grep -nE '^\s*@frappe\.whitelist' "$f" | grep -v 'methods=' | head -3 | sed 's/^/    /')
			[ -n "$m" ] && issues+=("Rule 11: declare methods=[\"POST\"] (changes) or methods=[\"GET\"] (reads):\n$m")
			m=$(python3 - "$f" <<'PY'
import ast, sys
tree = ast.parse(open(sys.argv[1]).read())
for fn in tree.body:
	if not isinstance(fn, ast.FunctionDef):
		continue
	if not any("whitelist" in ast.unparse(d) for d in fn.decorator_list):
		continue
	a = fn.args
	bad = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs if x.annotation is None]
	if a.kwarg:
		bad.append("**" + a.kwarg.arg)
	if bad:
		print(f"    {fn.lineno}: {fn.name}({', '.join(bad)})")
PY
)
			[ -n "$m" ] && issues+=("Rule 11: every whitelisted argument needs a type hint (no **kwargs for client input):\n$m")
		fi

		[[ $is_test == 1 || "$rel" == ai_assistant/tasks.py || "$rel" == ai_assistant/agent/runner.py || "$rel" == ai_assistant/evals/* ]] || {
			m=$(hit 'frappe\.db\.(commit|rollback)\(')
			[ -n "$m" ] && issues+=("frappe-code-review §1: no commit/rollback outside the job runner, tasks, and evals; the request or job owns the transaction:\n$m")
		}

		[[ "$rel" == ai_assistant/hooks.py ]] || {
			c=$(grep -cE '^\s*#' "$f")
			lines=$(grep -cvE '^\s*$' "$f")
			[ "$lines" -gt 20 ] && [ $((c * 5)) -gt "$lines" ] && issues+=("Comment density is high ($c comment lines of $lines). Keep comments minimal.")
		}
		;;
	ai_assistant/public/js/*)
		m=$(hit 'frappe\.client\.|frappe\.db\.(set_value|insert|delete_doc)|frappe\.xcall\(["'"'"']frappe\.')
		[ -n "$m" ] && issues+=("The chat UI calls ai_assistant.api.* only:\n$m")
		m=$(hit '\.innerHTML\s*=|\.html\((response|data|msg|text|content)')
		[ -n "$m" ] && issues+=("Model output must be rendered with frappe.markdown and sanitized, not injected as raw HTML:\n$m")
		m=$(hit '(sk-[A-Za-z0-9_-]{16,}|api_key\s*[:=])')
		[ -n "$m" ] && issues+=("Rule 7: no keys in JS; read settings from get_bootstrap:\n$m")
		;;
esac

[ ${#issues[@]} -eq 0 ] && exit 0
msg="ai_assistant invariant check on $rel:"
for i in "${issues[@]}"; do msg+=$'\n- '"$(printf '%b' "$i")"; done
msg+=$'\nSee .claude/references/invariants-checklist.md. Fix or justify.'
jq -n --arg m "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
