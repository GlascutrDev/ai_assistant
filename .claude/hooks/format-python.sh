#!/usr/bin/env bash
# PostToolUse(Write|Edit): ruff import-sort + format, pinned to the pre-commit ruff version.
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
case "$f" in
	*.py) ;;
	*) exit 0 ;;
esac
uvx ruff@0.14.10 check --select=I --fix --quiet "$f" && uvx ruff@0.14.10 format --quiet "$f"
