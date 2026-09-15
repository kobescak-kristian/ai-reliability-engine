# AGENTS.md — AI Reliability Engine

Tool-neutral routing guide for coding agents working in this repository. It points to
the sources that hold authority; it is not itself a source of truth.

## Repository purpose

AI Reliability Engine is an operational reliability layer between an AI classifier and
downstream operational systems. It sanitises input before the model call, validates every
AI output against a strict schema, applies a bounded fallback when output is invalid or
unavailable, routes uncertain and fallback cases to manual review, persists every decision
to an audit trail, and feeds decisions into notification and CRM integration paths.

## Authority and conflict handling

Where authority lives:

- `README.md`: public system description, claims, known limitations, and the Version Log.
  The Version Log is the documented history surface.
- `adr/`: material decisions and their rationale.
  - `adr/001-validation-before-routing.md`: the core validate-before-route decision and
    the fallback sequence.
  - `adr/002-remove-walkthrough-and-runbook.md`: removal of the walkthrough and runbook,
    and where their explanatory content was retained.
- `TECHNICAL_OWNERSHIP_GUIDE.md`: detailed design and code-ownership explanation for
  technical review.
- `ASSURANCE_ONE_PAGER.md`: assurance controls and risk summary.
- `evals/EVAL_RESULTS.md`: committed, measured evaluation evidence.
- The affected source files and `config/settings.py`: actual implementation behaviour.
- `.github/workflows/ci.yml`: the current automated verification path.

When sources disagree:

- An adopted ADR governs the decision it records.
- Documentation states intent and claims. Source and configuration state actual behaviour.
  Committed eval artifacts state what was observed in recorded runs.
- Surface every disagreement in your report. Never silently reconcile it by editing one
  side to match the other.
- If a requested change materially depends on an unresolved conflict, stop and ask for
  owner review before changing anything.

## Task routing

Starting points, not complete inventories:

| Task | Start here |
|---|---|
| System description, public claims | `README.md` |
| Input loading and sanitisation | `pipeline/input_handler.py`, `utils/sanitiser.py`, `models/schemas.py` |
| AI call and keyless simulation | `pipeline/ai_processor.py`, `config/settings.py` |
| AI output validation | `pipeline/validator.py`, `models/schemas.py`, `adr/001-validation-before-routing.md` |
| Fallback (retry, safe default) | `pipeline/fallback.py`, `pipeline/validator.py` |
| Routing and confidence threshold | `pipeline/router.py`, `config/settings.py` |
| Full local pipeline (CLI) | `main.py` |
| HTTP API | `api.py` |
| Persistence and audit trail | `utils/database.py`, `main.py` |
| Manual-review notifications (alert queue, Slack, email) | `utils/notifier.py` |
| Google Sheets CRM integration | `utils/sheets.py` |
| Evaluation evidence | `evals/EVAL_RESULTS.md`, `.github/workflows/ci.yml` |
| Assurance and technical ownership | `ASSURANCE_ONE_PAGER.md`, `TECHNICAL_OWNERSHIP_GUIDE.md` |
| Material decisions | `adr/` |
| Documentation and artifact validation | the affected artifact, `.githooks/validate_artifacts.py` |
| CI, hooks, publishing | `.github/workflows/ci.yml`, `.githooks/`, `.publicgate-allow` |

## Always-on constraints

Pipeline behaviour:

1. **Validate before routing.** No unvalidated model output may reach `pipeline/router.py`.
   This is the decision recorded in ADR-001. Both entry points (`main.py`, `api.py`) run the
   validator before the router.
2. **Fallback is bounded.** A validation failure runs `pipeline/fallback.py` before routing:
   at most one retry through the existing strict-prompt path (`MAX_RETRIES`), then the
   deterministic safe default constructed in code, flagged `MANUAL_REVIEW_FLAGGED`. Do not
   add unbounded or extra retry paths.
3. **Fallback records stay safe-routed.** The router checks `MANUAL_REVIEW_FLAGGED` before
   any category or confidence logic. A fallback-flagged record must never be auto-routed to
   a business action.
4. **Original validation evidence is preserved.** The persisted and alerted validation result
   describes the original AI output. Re-validating the fallback output is a consistency check
   only and must not overwrite the original failure evidence.
5. **Keyless simulation is the routine path.** A missing, empty, or `.env.example` placeholder
   `OPENAI_API_KEY` selects simulation mode (`config/settings.py`). Routine development and
   verification must not make a paid or real-model call. A real model run requires explicit
   owner authorization.
6. **Model-access failures stay visible.** Authentication rejection, transport or model errors,
   no usable response, and schema-invalid output must remain visible through the existing
   logging, validation, and fallback path. Never turn them into silent pass-through.
7. **Audit write comes before downstream work.** In both entry points each decision is written
   to SQLite before the manual-review notification, and in the CLI before the Google Sheets
   write. Do not add a path where downstream operational action happens from unvalidated
   output or skips this audit write. This is call ordering, not a crash-safety or
   transactional guarantee.

Evidence and history:

8. **Eval gates and results are evidence.** Committed evaluation results and the CI assertions
   in `.github/workflows/ci.yml` are final records. Do not change expected values, thresholds,
   or published failures after seeing a run to make verification pass. A deliberate new
   evaluation cycle defines and freezes its scorer or gate before it runs.
9. **No history rewrites.** External evidence references commits in this repository by hash.
   Do not rebase or amend pushed commits, and do not force-push.

Artifacts and files:

10. **Preserve the existing reviewer artifacts.**
    `ASSURANCE_ONE_PAGER.md`, `DEMO_SCRIPT.md`, and
    `TECHNICAL_OWNERSHIP_GUIDE.md` are legitimate governed artifacts in
    this repository. Do not remove, duplicate, regenerate, or demote them
    unless a separately authorized task requires it. Do not copy their
    changing content into this file.
11. **Other artifacts are trigger-gated.** Beyond the Tier 0 set (`README.md`, `adr/`,
    `LICENSE`, `AGENTS.md`) and the reviewer artifacts above, create a new documentation
    artifact only when a genuine material decision record in `adr/` cites its trigger.
    ADRs have no hard maximum. Version history stays in the `README.md` Version Log. If
    `.githooks/validate_artifacts.py` disagrees with this rule, surface the disagreement;
    do not edit the validator or merge decision records to satisfy it without an authorized
    task.
12. **No secrets or machine-local paths.** Never commit credentials, `.env`,
    `credentials.json`, or machine-specific absolute paths. Machine-specific values belong in
    gitignored local configuration.
13. **This file is guidance, not enforcement.** AGENTS.md is an instruction surface, not a
    security boundary. Enforcement lives in the hooks (`.githooks/`), CI
    (`.github/workflows/ci.yml`), and runtime validation in the pipeline.

## Verification

Keep verification keyless and offline.

1. Artifact check. Expect `Tier 0: PASS`.

   ```bash
   python .githooks/validate_artifacts.py .
   ```

2. Pipeline check. Run the keyless, CI-equivalent path. `.github/workflows/ci.yml` is the
   authority for the run and its frozen summary assertions: compare the output against those
   assertions and never edit them to fit a run. A local `.env` may hold real credentials, and
   variables already set in the environment take precedence over `.env`, so override them
   explicitly (Git Bash / POSIX shell):

   ```bash
   PYTHONUTF8=1 \
   OPENAI_API_KEY= \
   SLACK_ENABLED=false \
   EMAIL_ENABLED=false \
   GOOGLE_SHEETS_ID= \
   python main.py
   ```

   The config summary at the start of the run must show `simulation_mode: True`,
   `slack_enabled: False`, `email_enabled: False`, and `sheets_enabled: False`. If it does
   not, stop the run. The run creates or updates gitignored local files under `data/`
   (`pipeline.db`, `alerts.json`, `results.json`).

3. For changes to hooks, CI, or publishing, CI on the pushed commit (all matrix jobs) is the
   final check.

## Repository landmarks

- `data/sample_input.json` and the simulation seeds in `pipeline/ai_processor.py`
  (`SIMULATED`, `FORCED_FAILURES`) together determine the keyless run output that CI asserts.
  Changing either changes evaluation evidence.
- `architecture_v2.png` is the overview diagram; `architecture-v2-diagram.png` is the detailed
  technical diagram. Both are embedded in `README.md`.
