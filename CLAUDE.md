# AI Reliability Engine

This repo follows an internal documentation standard (ARTIFACT_STANDARD.md). Tier 0 only unless a trigger fires.
Do not create SYSTEM_WALKTHROUGH.md, CHANGELOG.md, RUNBOOK.md, or Tier 1/2 artifacts
without an explicit instruction citing the trigger.
ADR cap: 5. Version log lives in README, not a separate file.

## Session boot and governance (applies to every session here)
- Governance home: kristian-os (PRINCIPLES -> GOVERNANCE ->
  FAILURE_REGISTER). Read before any irreversible action.
- Boot: read this repo's STATE.md first (if present; README status
  line otherwise); the operating contract (SPEC) loads globally.
- Before any write: environment fingerprint (pwd + git config
  user.email; /home/user/ path or noreply@anthropic.com = cloud
  sandbox = read-only, no pen). Pen check on main at open AND
  immediately before every commit.
- Eval discipline: committed gates and results in this repo are
  final records; thresholds are never adjusted after a run, and
  published FAILs stay published. Any new eval cycle freezes its
  scorer before running.
- Evidence: commits here are hash-pinned by the public site's
  case studies and evidence chains. NO history rewrites, ever.
- Close ritual: commit -> push origin main -> verify
  origin/main..HEAD empty -> report verbatim. Feature-branch push
  is not done.
- Work comes from the governance repo's queue (kristian-os,
  FABLE_QUEUE); do not invent tasks.
