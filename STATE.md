# STATE — ai-reliability-engine

**Classification:** PROJECT · T0 · **Flagship** (canonical validator's `CURRENT_FLAGSHIP`; `domains/github-ops/STATE.md` Engine Status table).

**RECONSTRUCTED** (GOVERNANCE.md Build-repo STATE rule, clause 7): derived from git history and the README Version Log at scaffold time (2026-09-19, Q-72(f)), not written contemporaneously. Reconstructed entries are retrospective evidence, not contemporaneous record — the commit that adds this file begins the contemporaneous record going forward.

## Current state

**Status: Complete — v2.0** (README). Eight-stage pipeline: sanitize → AI classify (keyless-simulation by default) → validate output against a strict schema → bounded fallback (one retry, then a deterministic safe default) → route → persist to audit trail → manual-review notification → CRM integration. Two ADRs: `adr/001-validation-before-routing.md` (validate before routing), `adr/002-remove-walkthrough-and-runbook.md` (removed the pre-standard SYSTEM_WALKTHROUGH.md/RUNBOOK.md, content salvaged into TECHNICAL_OWNERSHIP_GUIDE.md).

## Version Log (from README, verbatim)

| Version | Date | Change |
|---|---|---|
| v2.0 | 2026-04-22 | Initial release — 8-stage pipeline, validation, fallback, routing, Sheets CRM, Slack/email alerts |
| v2.0 | 2026-04-23 | Architecture diagrams and repository structure documented |
| v2.0 | 2026-06-17 | System Context expanded to five-engine system |
| v2.0 | 2026-06-19 | Added ADR-001, eval results, assurance one-pager, runbook |
| v2.0 | 2026-07-04 | Removed SYSTEM_WALKTHROUGH.md and RUNBOOK.md per ARTIFACT_STANDARD v2.1 (ADR-002); traces merged into TECHNICAL_OWNERSHIP_GUIDE |
| v2.0 | 2026-07-04 | Audit remediation: fix validation-result persistence, Windows console encoding, sanitiser ordering, Sheets RAW writes; docs re-derived from live run |

## Build history since the Version Log's last entry (from `git log --reverse`)

- **2026-07-07** (`aeba7a4`, `8ad2153`, `8b0f2df`) — Assurance risk register added (9 risks, code-verified mitigations); explicit placeholder-key detection + surfaced auth failures; private-repo reference scrubbed from the risk register.
- **2026-07-10** (`bb96ab2`) — Simulated euros labeled in the worked example (Q-28).
- **2026-07-11** (`d47f1aa`) — CLAUDE.md: session boot + governance pointer.
- **2026-07-24** (`728c815`) — Canonical pre-commit local-path guard added (Q-48 wave 1).
- **2026-07-27** (`a137867`, `075e563`) — Keyless 3-OS eval CI workflow + publish-gate allowlist; CI badge and per-OS coverage note.
- **2026-08-03** (`307c226`) — Publish-gate coverage canary added.
- **2026-08-04** (`1cee829`, `92a7839`, `fa1028d`) — Allowlist migrated to entry-exact form; Apache-2.0 license added; Q-35 hook rollout (first-push guard, `decisions/` acceptance, comment sweep).
- **2026-09-15** (`0aa463a`) — Canonical AGENTS.md router adopted (Q-93).
- **2026-09-19** (this commit) — Q-72(f): STATE.md added (this file); validator gains a STATE.md-existence check, the obsolete 5-record decision cap is removed, and flagship/Tier-1 handling (`TIER1_ARTIFACTS`, `CURRENT_FLAGSHIP`/`IS_FLAGSHIP`) is added to this repo's own local validator copy, mirroring canonical, since this repo *is* the flagship and already carries `ASSURANCE_ONE_PAGER.md`/`TECHNICAL_OWNERSHIP_GUIDE.md`/`DEMO_SCRIPT.md` as governed reviewer artifacts (`AGENTS.md` constraint 10) the local validator previously didn't recognize at all. README's stale "(capped at 5)" repository-tree wording corrected in the same commit.

## Open loops

None on disk beyond the Q-72(f) items closed by this commit.
