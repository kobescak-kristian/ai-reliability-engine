# System Card — AI Reliability Engine

A system-level transparency card: what this system is, what its evidence
shows, and where it stops. Practice signal for technical reviewers, not a
compliance document. Headline figures are written as `FIG:` lines; each
figure token appears verbatim in the named source file.

## 1. Header

- System: AI Reliability Engine, v2.0
- Author: Kristian Kobescak
- Date: 2026-10-07
- License: Apache-2.0 (`LICENSE`)
- Repository: https://github.com/kobescak-kristian/ai-reliability-engine

## 2. Scope and status

- Portfolio system, not deployed, no users.
- No model is trained or fine-tuned here. A third-party classifier is
  called only when an API key is configured; the default and the CI path
  run a keyless simulation with seeded responses keyed by lead ID
  (`pipeline/ai_processor.py`).
- Input data is a bundled sample set with no real personal information
  (`data/sample_input.json`).
- What the evidence shows: the validation, fallback, routing, audit and
  alert controls behave as designed on a fixed record set, on three
  operating systems and two Python versions, on every push and pull
  request to main.
- What it does not show: classification accuracy on real traffic,
  behaviour under production load, or the quality of a live model's
  answers.

## 3. Purpose and intended use

Sits between an AI classifier and operational systems (sales CRM,
spreadsheet queue, human review). It validates every model output
against a strict schema, applies a bounded fallback when output is
invalid or missing, routes uncertain or failed cases to manual review,
and records every decision before any downstream action. Intended
audience: teams putting AI classification into business workflows, and
reviewers assessing how AI risk is controlled.

## 4. Out of scope

- Classifying new, unseen text without an API key (the simulator returns
  no output for unknown leads, which takes the fallback path).
- Judging whether a schema-valid answer is correct: the validator checks
  form, not truth.
- Production operation: no API authentication, no data retention policy,
  SQLite only (section 11).
- Items that do not apply at all are listed in section 16.

## 5. Architecture and components

Eight-stage linear pipeline (diagrams: `architecture_v2.png`,
`architecture-v2-diagram.png`):

1. Input and sanitise — `pipeline/input_handler.py`, `utils/sanitiser.py`
2. AI classification (or keyless simulation) — `pipeline/ai_processor.py`
3. Validation — `pipeline/validator.py`, `models/schemas.py`
4. Fallback — `pipeline/fallback.py`
5. Routing — `pipeline/router.py`
6. Audit persistence — `utils/database.py` (SQLite, one run ID per run)
7. Manual-review alerts — `utils/notifier.py` (local queue always;
   Slack and email optional)
8. Spreadsheet CRM write — `utils/sheets.py` (CLI path with credentials
   only)

Entry points: `main.py` (CLI) and `api.py` (FastAPI). Both validate
before routing and write the audit record before the alert.

## 6. Models and dependencies

- Classifier: OpenAI `gpt-4o-mini` by default, configurable with
  `OPENAI_MODEL` (`config/settings.py`); low temperature, structured JSON
  output required.

FIG: temperature=0.1 | SOURCE: pipeline/ai_processor.py

- The model name is not pinned to a dated snapshot, so a provider-side
  model change could alter answers (section 12).
- Python dependencies: the nine direct dependencies are pinned with `==`
  in `requirements.txt` (Pydantic v2, FastAPI, Uvicorn, OpenAI SDK,
  python-dotenv, httpx, pytest, gspread, google-auth); transitive
  dependencies are not pinned.

## 7. Design decisions and trade-offs

- Validate before routing, with a bounded fallback:
  `adr/001-validation-before-routing.md`.
- Documentation kept to what has a reader:
  `adr/002-remove-walkthrough-and-runbook.md`,
  `adr/003-system-card-replaces-assurance-one-pager.md`.
- Confidence threshold read from an environment variable, so it changes
  without a code change; SQLite for zero-dependency persistence (trade-off:
  not suitable for distributed deployment).

## 8. Data

- `data/sample_input.json`: 51 entries, 50 unique lead IDs (one lead is
  submitted twice to exercise repeat-lead handling).
- Seeded simulation responses (`SIMULATED`) and forced invalid responses
  (`FORCED_FAILURES`) live in `pipeline/ai_processor.py`. Three records
  force invalid outputs (bad category, out-of-range confidence, empty
  reason); three are rejected by the sanitiser (empty, whitespace-only,
  too short); one has no simulation entry.
- Known artifacts of the synthetic set: a forced-invalid record also
  fails its retry (intentional, for reproducibility); the 2000-character
  truncation path is not exercised (the longest input is 1262
  characters); details in `evals/EVAL_RESULTS.md`.

## 9. Evaluation methodology

- Deterministic keyless run of the full pipeline (`python main.py`); CI
  checks for the exact committed summary lines on every push and pull
  request to main.

FIG: os: [ubuntu-latest, macos-latest, windows-latest] | SOURCE: .github/workflows/ci.yml

FIG: python-version: ['3.12', '3.14'] | SOURCE: .github/workflows/ci.yml

- A second CI job runs the unit tests over the validator, router and
  fallback, keyless by construction.
- Metrics are control-behaviour counts (decisions by type, fallbacks,
  alerts), because the claim is about controls, not model accuracy.

## 10. Evaluation results

Keyless simulation counts asserted in CI (documented live run:
`evals/EVAL_RESULTS.md`, run ID below):

FIG: Total records   : 51 | SOURCE: .github/workflows/ci.yml

FIG: FinalDecision.SEND_TO_SALES: 22 | SOURCE: .github/workflows/ci.yml

FIG: FinalDecision.ARCHIVE: 10 | SOURCE: .github/workflows/ci.yml

FIG: FinalDecision.MANUAL_REVIEW: 19 | SOURCE: .github/workflows/ci.yml

FIG: Fallbacks       : 7 | SOURCE: .github/workflows/ci.yml

FIG: Alerts sent     : 19 | SOURCE: .github/workflows/ci.yml

FIG: run_20260704_031434_8cda36 | SOURCE: evals/EVAL_RESULTS.md

FIG: 23 pytest functions | SOURCE: README.md

All seven fallbacks (three forced invalid outputs, four records with no
usable output) ended in manual review; none reached an automatic action.

## 11. Capabilities and limitations

Does reliably: rejects outputs with a category outside the allowed set,
confidence outside 0.0-1.0, or a missing or empty field; retries once,
then assigns a code-built safe default; routes fallback-flagged records
to manual review before any category logic; persists every decision with
its run ID.

Degrades or stops:

- A schema-valid but wrong answer passes validation.
- One retry, no backoff.

FIG: MAX_RETRIES = 1 | SOURCE: pipeline/fallback.py

- No API authentication on the HTTP endpoints.
- SQLite only; spreadsheet writes can hit API rate limits on large
  batches; the API path skips the spreadsheet write.
- No data retention or deletion policy is defined.

## 12. Failure modes and risks

Each row was re-checked against the code at the revision this card was
written from.

| Risk | Control in this system | Residual risk |
|---|---|---|
| Invalid model output reaches a workflow | Validator, one strict retry, safe default, fallback-first routing | Wrong but schema-valid answers pass |
| Silent fallback when the API key is missing or a placeholder | `config.simulation_mode()` treats empty, missing and the example placeholder key as simulation and logs why; a rejected key is logged as an error before fallback | Key validity across environments still depends on people |
| Run stops part-way | Console streams use UTF-8 with replacement (`utils/logger.py`), removing the known crash vector | No automated reconciliation of a partial run |
| Alert or spreadsheet write fails after the decision | Audit record and local alert queue are written first; Slack and email failures are caught and logged | No automatic resend |
| Formula injection into the spreadsheet | Rows are written with `value_input_option="RAW"` (`utils/sheets.py`) | No test enforces RAW mode |
| Cost runaway on retries | One retry; simulation for development | No spend ceiling in the code |
| Prompt injection inside input text | Script and style blocks removed before tag stripping, control characters removed, length bounds | Plain-text instructions are not detected |
| Threshold goes stale | One configurable threshold, read in one place | No automatic recalibration |
| Provider model changes | Model name configurable | Not pinned to a dated snapshot |

Adversarial testing is limited to the markup, empty and short inputs in
the sample set; no red-team run was made.

## 13. Human oversight and control points

- Every manual-review decision is written to the local alert queue
  (`data/alerts.json`); Slack and email alerts are off by default and
  enabled by configuration.
- Alerts are acknowledged through `PATCH /alerts/{lead_id}/acknowledge`.
- High-value leads below the confidence threshold are never actioned
  automatically.

FIG: "CONFIDENCE_THRESHOLD", "0.60" | SOURCE: config/settings.py

- The model only classifies; a deterministic rule table makes every
  routing decision.

## 14. Security posture

- Secrets come from environment variables or a local `.env`; `.env`,
  the spreadsheet service-account file and runtime data files are
  gitignored.
- The keyless simulation is the default and the CI path; CI makes no
  model call.
- Input is bounded before any model call.

FIG: MAX_INPUT_LENGTH = 2000 | SOURCE: utils/sanitiser.py

FIG: if len(text) < 5: | SOURCE: utils/sanitiser.py

- The HTTP API has no authentication (section 11).
- Changes reach the main branch through pull requests with required CI
  checks.

## 15. Version history and lifecycle

- 2026-04-22: v2.0 released (eight-stage pipeline).
- 2026-07-04: audit remediation; walkthrough and runbook removed (ADR-002).
- 2026-10-04: unit tests added as a second CI job.
- 2026-10-07: direct dependencies pinned; this card replaces the earlier
  assurance one-pager (ADR-003).

Full log: README "Version Log". This card changes when the system
meaningfully changes, not per commit.

## 16. Not-applicable register

- Model training data and training procedure: no model is trained here.
- Fairness or demographic evaluation: the sample set is synthetic lead
  text about businesses, with no real personal information.
- Production monitoring and incident metrics: the system is not deployed.
- Energy and compute reporting: no training; inference only when a key
  is configured.
- Regulatory conformity statements: this card is a practice signal, not
  a compliance document.
