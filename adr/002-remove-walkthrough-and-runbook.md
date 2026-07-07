# ADR-002 — Remove SYSTEM_WALKTHROUGH.md and RUNBOOK.md

**Status:** Accepted
**Date:** 2026-07-04
**Author:** Kristian Kobescak

---

## Context

This repo adopted an internal documentation standard, ARTIFACT_STANDARD.md (v2.1), for documentation.
Under that standard, Tier 0 is the only artifact tier built by default:
README.md (with problem, solution, system, outcome, and a version-log
section) plus a capped adr/ folder. SYSTEM_WALKTHROUGH.md and RUNBOOK.md
are Tier 1/2 artifacts — each requires a named reader and a dated trigger
before it is built. Neither had one; both existed only because they were
added before the standard was adopted here.

A validator (`.githooks/validate_artifacts.py`, run on `pre-push` via
`core.hooksPath`) now flags either file's existence unless an ADR in this
folder cites its trigger. No such trigger exists for either file.
Note: `core.hooksPath` is per-clone local git configuration — it does not
propagate through `git clone`; each clone must run
`git config core.hooksPath .githooks` for the hook to fire.

## Decision

**Delete SYSTEM_WALKTHROUGH.md and RUNBOOK.md.** Before deletion, both
were audited line-by-line against README.md and TECHNICAL_OWNERSHIP_GUIDE.md
to identify any explanatory content (how the system works, why it behaves
as it does) not already captured elsewhere:

- SYSTEM_WALKTHROUGH.md contributed two pieces of content found nowhere
  else: the `lead_001` happy-path trace and the `lead_037` failure-path
  trace. Everything else in the file (problem framing, architecture
  description, fallback statistics, audit-field table, known limitations,
  "what this demonstrates" positioning) was already duplicated in
  README.md and/or TECHNICAL_OWNERSHIP_GUIDE.md.
- RUNBOOK.md contained no explanatory content outside what is already in
  README.md/TECHNICAL_OWNERSHIP_GUIDE.md — every section was operational
  (install, run, troubleshoot, recover). Purely operational content is not
  salvaged; it returns in a RUNBOOK.md if and when a Tier 2 trigger fires
  for this repo.

## Alternatives Considered

**Keep both files, add an ADR citing "portfolio depth" as the trigger**
Rejected — "portfolio depth" is not a named reader with a dated need; it is
the exact pattern the standard exists to prevent (documentation built
because it's possible, not because someone needs it now).

**Delete without auditing for salvageable content**
Faster, but risks silently losing the two worked-example traces, which are
the kind of concrete artifact a technical reviewer actually reads. Rejected
in favor of a one-time audit before deletion.

## Consequences

**Positive:**
- Repo returns to Tier 0 compliance; `validate_artifacts.py` passes
- Documentation surface area shrinks to what a 30-second reader and a
  technical reviewer each need, with no redundant restating of the same
  facts across four files
- Explanatory content salvaged into TECHNICAL_OWNERSHIP_GUIDE.md before
  removal (the two worked-example traces; RUNBOOK.md had nothing to
  salvage)

**Trade-offs:**
- If someone needs a copy-paste operational runbook (start/stop/recover
  commands) before a Tier 2 trigger legitimately fires, they will need to
  reconstruct it from README.md and the codebase directly
- Future readers who bookmarked SYSTEM_WALKTHROUGH.md or RUNBOOK.md by
  filename will hit a 404 in repo history rather than a redirect
