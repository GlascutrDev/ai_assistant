#!/usr/bin/env bash
# SessionStart: report bench/site readiness so Claude doesn't rediscover it each session.
bench_root=$(cd "$CLAUDE_PROJECT_DIR/../.." && pwd)
site="today.localhost"
test_site="today-test.localhost"
out=("ai_assistant session context (bench: $bench_root, site: $site)")

cfg="$bench_root/sites/$site/site_config.json"
if [ -f "$cfg" ]; then
	dev=$(jq -r '.developer_mode // 0' "$cfg")
	installed=$(jq -r '(.installed_apps // []) | index("ai_assistant") != null' "$cfg")
	[ "$dev" = "1" ] || out+=("- developer_mode is OFF: run 'bench --site $site set-config developer_mode 1' before creating DocTypes")
	[ "$installed" = "true" ] || out+=("- ai_assistant not installed on $site: 'bench --site $site install-app ai_assistant'")
else
	out+=("- site config not found at $cfg")
fi

test_cfg="$bench_root/sites/$test_site/site_config.json"
if [ -f "$test_cfg" ]; then
	t_inst=$(jq -r '(.installed_apps // []) | index("ai_assistant") != null' "$test_cfg")
	t_allow=$(jq -r '.allow_tests // false' "$test_cfg")
	[ "$t_inst" = "true" ] || out+=("- ai_assistant not installed on test site: 'bench --site $test_site install-app ai_assistant'")
	[ "$t_allow" = "true" ] || [ "$t_allow" = "1" ] || out+=("- test site: allow_tests off ('bench --site $test_site set-config allow_tests true')")
else
	out+=("- test site $test_site missing. Never run tests on $site.")
fi

branch=$(git -C "$CLAUDE_PROJECT_DIR" branch --show-current 2>/dev/null)
dirty=$(git -C "$CLAUDE_PROJECT_DIR" status --porcelain 2>/dev/null | wc -l)
out+=("- git: branch ${branch:-?}, $dirty changed file(s)")

printf '%s\n' "${out[@]}"
