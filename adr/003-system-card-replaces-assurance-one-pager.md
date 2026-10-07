# ADR-003 — SYSTEM_CARD.md replaces ASSURANCE_ONE_PAGER.md

**Status:** Accepted
**Date:** 2026-10-07
**Author:** Kristian Kobescak

---

## Context

`ASSURANCE_ONE_PAGER.md` was added on 2026-06-19 as a risk and assurance
summary for reviewers. The documentation standard this repository
follows (ARTIFACT_STANDARD.md, v2.4 and later) retired that artifact
name and replaced it with a repository-root `SYSTEM_CARD.md` built from
a fixed 16-block template, with one rule the one-pager never had: every
headline figure is written as a `FIG: <token> | SOURCE: <path>` line, and
a publication gate checks that the token still appears in the named
file. This repository is the documentation flagship, so it is one of the
two repositories the standard assigns a system card.

The one-pager had also drifted from the code. Its risk register states
that the repository has no automated tests; since 2026-10-04 a pytest
suite over the validator, router and fallback runs in CI.

## Decision

**Add `SYSTEM_CARD.md` at the repository root and delete
`ASSURANCE_ONE_PAGER.md`.** Before deletion, every claim in the one-pager
was re-checked against the code at the starting revision:

- Carried into the card (sections 6, 11, 12, 13 and 14): purpose and
  intended use, the model role and temperature, the deterministic
  controls, human oversight points, failure handling, the audit trail,
  the privacy notes, the production gaps (the missing pipeline health
  monitoring is listed in section 16, since the system is not
  deployed), and each risk-register row whose mitigation the code still
  shows.
- Not carried: the statement that no automated tests exist (false since
  2026-10-04), commit-level remediation detail that belongs to history,
  and rating rows marked TODO with no assessment behind them.

`AGENTS.md`, the README repository tree and `STATE.md` now route to the
card. The one-pager stays readable in git history.

## Consequences

- Reviewers get one transparency artifact, ordered so that scope and
  limits come before results.
- Headline figures can no longer drift silently: the publication gate
  blocks a card figure that its source file no longer contains.
- The repository's artifact validator allows `SYSTEM_CARD.md` because
  this record cites it.
