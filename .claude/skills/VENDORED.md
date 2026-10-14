# Vendored skills

These skills are copied unchanged from the official Frappe skills repo (via `apps/today_ops/.claude/skills`). Don't edit them. Put project rules in our own skills, agents, references, and `CLAUDE.md`, which take precedence.

| | |
|---|---|
| Source | https://github.com/frappe/skills |
| Commit | `0bef982e933705c30706efc1db3bc3bc5e7aca62` (2026-09-30) |
| Vendored on | 2026-10-14 (copied from today_ops) |
| License | The upstream repo has no license file. Internal use in this project only; don't redistribute. |

## Included

| Skill | Use here |
|---|---|
| `frappe-app-dev/` | General Frappe reference. Load only the reference file you need (doctypes, controllers, hooks, permissions, background-jobs, realtime, testing, frontend-desk). |
| `frappe-code-review/` | Generic review checklist. `security-reviewer` runs it after the project checklist. |
| `code-style/` | Small functions, files of 300 lines or fewer, public functions first. |
| `technical-writing/` | Simplified Technical English for README, SPEC, module READMEs, commits, and PRs. |
| `deep-app-audit/` | User-invoked audit: `/deep-app-audit apps/ai_assistant`. Required before users outside System Manager get access (SPEC §16). |

## Where our files override upstream

- **API layout:** upstream prefers doc-level controller methods. ai_assistant keeps an `ai_assistant/api/` package (`chat.py`, `settings.py`), because chat endpoints are not tied to one document.
- **Permissions:** upstream examples sometimes use `ignore_permissions=True` in services. In ai_assistant, tools must never bypass permissions (CLAUDE.md rule 1).
- **Frontend:** upstream `frontend-vue.md` does not apply. The chat UI is Desk JS (`frontend-desk.md`).
- **Tests:** our test site is `today-test.localhost`.

## Update

```sh
SHA=<new commit>
cd apps/ai_assistant/.claude/skills
curl -s "https://api.github.com/repos/frappe/skills/git/trees/$SHA?recursive=1" \
  | jq -r '.tree[] | select(.type=="blob") | .path' \
  | grep -E '^skills/(frappe-app-dev|frappe-code-review|code-style|technical-writing|deep-app-audit)/' \
  | while read -r p; do d=${p#skills/}; mkdir -p "$(dirname "$d")"; curl -sfL "https://raw.githubusercontent.com/frappe/skills/$SHA/$p" -o "$d"; done
```

Then update the commit above and check the upstream diff against the overrides listed here.
