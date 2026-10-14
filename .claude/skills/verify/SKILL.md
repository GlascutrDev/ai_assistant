---
name: verify
description: Verify an ai_assistant change before reporting done — lint, the relevant tests via the test-runner agent, then the security-reviewer agent. Use when finishing a feature or when asked to "check", "verify", or "is this ready".
---

# Verify a change

1. List changed files: `git -C /home/nazmul/Desktop/AROMA/apps/ai_assistant status --porcelain`.
2. Delegate to the `test-runner` agent: lint, plus the test modules that cover the changed files (tools → `test_tools_*`, agent → `test_agent_*` and `test_acceptance_*`, attachments → `test_attachments`, api → `test_api_*`). Ask for a pass/fail summary only.
3. If everything passes, delegate to the `security-reviewer` agent with the changed paths.
4. If a prompt, tool docstring, or model setting changed, suggest an evaluation run (`eval-case` skill). Don't start one without the user's approval, because it calls paid providers.
5. Report:
   - one line per check
   - reviewer findings (`file:line`, rule, scenario)
   - docs still to update (SPEC, CLAUDE diagram, module README)

Don't claim "done" while a check fails or a finding is open. Before users outside System Manager get access, remind the user to run `/deep-app-audit apps/ai_assistant` (user-invoked only).
