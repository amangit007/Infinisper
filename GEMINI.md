# GEMINI.md

**This file intentionally contains no rules of its own.**

Antigravity loads both `AGENTS.md` and `GEMINI.md` as Rules, and resolves conflicts in favour of
`GEMINI.md`. Duplicating guidance across two files that are read together is a drift trap: the copies
diverge, the wrong one wins, and nobody notices.

So the single source of truth for this repository is:

## → [`AGENTS.md`](AGENTS.md)

Read it in full. It covers the stack, the nine invariants, the repository layout, the conventions, and
the list of things that look like bugs but are deliberate.

Then read [`docs/PLAN.md`](docs/PLAN.md) to see which phase the project is in.

---

If a future Antigravity-specific rule is ever genuinely needed — something that must not apply to
other agents — add it below this line, and only then. Everything else belongs in `AGENTS.md`.
