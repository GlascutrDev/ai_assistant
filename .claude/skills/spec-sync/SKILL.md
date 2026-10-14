---
name: spec-sync
description: Reconcile SPEC.md, CLAUDE.md, and module READMEs with the code or a new product decision — record answered open questions, new [Decision]s, resolved [Verify] items, and diagram updates. Use when the user answers an open question, changes a requirement, or asks to update the docs or spec.
---

# Keep SPEC / CLAUDE / READMEs in sync

Source order: explicit user corrections > the product request > SPEC.md.

1. **Answer to an open question:** mark the SPEC §15 row Resolved with the answer and date, apply it to every affected section (grep the terms), and list code that now contradicts SPEC.
2. **Choice forced by the build:** add **[Decision]** inline in the relevant section, one sentence with the reason.
3. **A [Verify] item checked:** replace the marker with the verified fact and its source (`apps/frappe/...` file, or the Context7 doc). Move the fact into `.claude/references/` if code will rely on it, and remove it from the CLAUDE.md "Gotchas to verify" list.
4. **CLAUDE.md:** update the diagram for any added or removed DocType, tool, node, middleware, evaluator, endpoint group, or job. Change rules only when the user asks.
5. **Module READMEs** are for developers and agents; the root `README.md` is for users and admins only.
6. Write in Simplified Technical English (vendored `technical-writing` skill).
7. Finish with: changed sections, and code now out of date with the docs.
