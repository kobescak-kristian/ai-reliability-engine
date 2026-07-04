# Technical Ownership Sheet — AI Reliability Engine

> Interview preparation and technical ownership reference.
> Connects README claims to code structure.
> For code-running instructions see README.md.
> Worked examples (happy path / failure path) are below in this document.

---

## 1. Owner Summary

This system is a validation and fallback layer that sits between an AI classifier and operational systems. The core problem it solves is that AI output is probabilistic — a well-prompted model still returns wrong categories, out-of-range confidence scores, and empty fields — and most downstream systems do not handle that gracefully. This system catches every invalid output before it causes a wrong routing decision, applies a structured retry and safe-default fallback, and routes uncertain cases to human review rather than auto-actioning them. Every decision is written to SQLite with a run ID, so any pipeline run is fully reconstructable. The system also writes to Google Sheets and sends Slack and email alerts on manual review cases, closing the operational loop. It runs in simulation mode without an API key, which means the full pipeline including every failure mode is demonstrable without external dependencies. The known limitations — no API auth, SQLite only, single retry — are documented deliberately, not hidden.

---

## 2. System Purpose

**Business problem:** AI classifiers fail silently. When they return garbage, the garbage reaches operations. This system prevents that.

**User/team this is for:** Operations or AI teams running AI inside business workflows — sales automation, lead routing, CRM enrichment — where a wrong classification has a real downstream cost.

**What risk it prevents:** Invalid AI output reaching a sales team, being written to a CRM, or triggering a wrong automated action without any human awareness.

**What this system is not:**
- Not a model. It does not classify — it validates and routes what the AI returns.
- Not a rule-based classifier. Rules can't handle ambiguous, mixed-signal inputs; the AI does that. This system makes the AI's output safe.
- Not production-deployed. This is a portfolio-grade implementation with documented production gaps.

---

## 3. High-Level Flow

```
Input (JSON file or API POST)
  → input_handler.py     — load records, move control metadata into record
  → sanitiser.py         — strip HTML, reject too-short/empty inputs
  → ai_processor.py      — call OpenAI or return simulation response
  → validator.py         — check category, confidence range, reason
      if FAIL → fallback.py — retry with strict prompt → safe default if retry fails
  → router.py            — deterministic rule table → final decision
  → notifier.py          — Slack + email on manual_review
  → sheets.py            — write to Google Sheets (Action Queue + history tab)
  → database.py          — persist all fields to SQLite with run ID
```

Every stage has a defined failure behaviour. No stage silently passes bad data to the next.

---

## 4. Entry Points

**CLI (run full pipeline locally):**
```bash
python main.py
```
File: `main.py` — entry point, orchestrates all 8 stages, writes `data/results.json`.

**API (HTTP interface):**
```bash
uvicorn api:app --reload --port 8000
```
File: `api.py` — defines all endpoints. Swagger UI at `http://localhost:8000/docs`.

**Endpoints that trigger the full pipeline:**
- `POST /qualify` — single lead
- `POST /qualify/batch` — up to 50 leads under one shared run ID

**Read-only endpoints (no pipeline execution):**
- `GET /audit`, `GET /audit/{lead_id}`, `GET /alerts`, `GET /stats`, `GET /health`
- `PATCH /alerts/{lead_id}/acknowledge`

---

## 5. Input Data

**What comes in:** Unstructured lead text as a JSON record.

**Expected fields:**
- `id` — string, required (e.g. `"lead_001"`)
- `raw_text` — string, required (the lead content to classify)
- `metadata` — optional dict (`source`, `region`, `company_size`)

**Where schemas are defined:** `models/schemas.py` — `InputRecord`, `AIOutput`, `ValidationResult`, `PipelineResult`, and the enums `Category`, `FinalDecision`, `FallbackAction`.

**Sample input:** `data/sample_input.json` — 51 entries covering clean, ambiguous, borderline, malformed, and forced-failure cases.

**What the sanitiser rejects** (`utils/sanitiser.py`):
- Null or non-string input
- Empty string after HTML stripping
- Input under 5 characters after cleaning (e.g. `"Hi"` → rejected)
- Whitespace-only input

**What the sanitiser transforms but does not reject:**
- HTML tags and script blocks — stripped to plain text
- Input over 2000 characters — truncated
- Control characters — removed

Records rejected by the sanitiser never reach the AI call. They are logged and skipped.

---

## 6. Validation Layer

**Input sanitisation:** `utils/sanitiser.py` — fires before the AI call, operates on raw text.

**Schema/data models:** `models/schemas.py` — Pydantic v2 models used at every pipeline boundary.

**AI output validation:** `pipeline/validator.py` — fires after the AI call returns.

**Rules enforced** (all three must pass):
1. `category` must be in `{"high_value", "low_value", "unknown"}` — any other string fails
2. `confidence` must be a float in `[0.0, 1.0]` — values like `1.85` or `-0.3` fail
3. `reason` must be a non-empty string after stripping whitespace

**What a `None` response triggers:** `validator.py` line 10–12 — if `ai_output` is `None` (model call failed or returned non-JSON), validation returns `valid=False` immediately with `"AI returned no output"`.

**Key design point:** Pydantic v2 at every boundary means data cannot flow between stages without passing a schema check. There is no `dict` being passed around unchecked.

---

## 7. Model Call Layer

**Where the call happens:** `pipeline/ai_processor.py` — function `call_openai()`.

**Model used:** `gpt-4o-mini`, configurable via `OPENAI_MODEL` env var (`config/settings.py` line 17).

**What format is requested:** Structured JSON only. The system prompt explicitly instructs the model to return `{"category": ..., "confidence": ..., "reason": ...}` with no markdown or extra text.

**Strict prompt (used on retry):** A shorter, stricter version of the system prompt (`STRICT_SYSTEM_PROMPT` in `ai_processor.py`) is used when `strict=True` is passed — this is the retry path from `fallback.py`.

**Simulation mode:** When `OPENAI_API_KEY` is not set, `call_openai()` calls `_simulate()` instead of the live API. `_simulate()` returns pre-seeded responses from the `SIMULATED` dict (46 records) and `FORCED_FAILURES` dict (3 records with intentionally invalid outputs).

**When no API key is present:** `config.simulation_mode()` returns `True`. The full pipeline runs with simulated responses. Every failure mode is demonstrable without a key.

**Temperature:** 0.1 — kept low for consistency.

---

## 8. Fallback and Failure Handling

**What triggers fallback:** Any `ValidationResult` with `valid=False` from `pipeline/validator.py`.

**Where fallback lives:** `pipeline/fallback.py` — `handle_fallback()`.

**Retry:** One retry (`MAX_RETRIES = 1`), using `strict=True` which passes the stricter prompt to the AI call.

**If retry passes:** Returns the retried output with `FallbackAction.RETRY`. Pipeline continues normally.

**If retry also fails:** Assigns the safe default constructed in code:
- `category="unknown"`, `confidence=0.0`, `reason="System default — AI output failed validation after retry."`
- This is guaranteed to pass validation. Returns `FallbackAction.MANUAL_REVIEW_FLAGGED`.

**Why fallback/unknown routes to manual review:** The router (`pipeline/router.py` line 19–21) checks `MANUAL_REVIEW_FLAGGED` first, before any category logic. A fallback-flagged record cannot accidentally route to `send_to_sales` regardless of what the safe default category is.

**Intentionally demonstrated failure modes** (seeded in `data/sample_input.json` via `_force_invalid` metadata key):
- `lead_037` — bad category (`"maybe_value"`)
- `lead_038` — out-of-range confidence (`1.85`)
- `lead_039` — empty reason field

All three exhaust the single retry and receive the safe default. This is intentional for demo reproducibility.

---

## 9. Routing Logic

**File:** `pipeline/router.py` — `route()` function.

| Check order | Condition | Decision |
|---|---|---|
| 1st | `fallback_action == MANUAL_REVIEW_FLAGGED` | `manual_review` — no further checks |
| 2nd | `category == "high_value"` AND `confidence >= 0.60` | `send_to_sales` |
| 3rd | `category == "high_value"` AND `confidence < 0.60` | `manual_review` |
| 4th | `category == "low_value"` | `archive` |
| 5th | anything else (including `"unknown"`) | `manual_review` |

**Threshold:** `config.CONFIDENCE_THRESHOLD`, default `0.60`, set via env var. No code change needed to adjust it.

**Why this is operationally safer than direct AI action:** The AI never decides what happens. It only classifies. The router maps that classification to a business action using a rule table a non-technical stakeholder can read and verify. Changing the routing logic does not require touching the AI call or the validation layer. The confidence threshold separates "AI is probably right" from "AI is uncertain" without suppressing the uncertain case — it escalates it.

---

## Worked Examples: Happy Path and Failure Path

**Happy Path — `lead_001`**

Input:
```
"Enterprise client requested a demo of our full platform.
 Budget confirmed at 50,000 EUR annually.
 CFO and CTO both attending the call."
```

Pipeline trace:
1. Sanitiser: input is clean, no transformation needed
2. AI Processor: returns `{category: "high_value", confidence: 0.95, reason: "Enterprise demo with confirmed 50k EUR annual budget and C-suite attendance."}`
3. Validator: all fields valid — passes
4. Router: `high_value` + `confidence 0.95 ≥ 0.60` → `send_to_sales`
5. Notify: no alert (not `manual_review`)
6. Google Sheets: written to Action Queue tab and Sales tab
7. SQLite: decision persisted with run ID

Result: `send_to_sales`. No human intervention required. Decision traceable by lead ID.

**Failure Path — `lead_037`**

Input:
```
"Small startup exploring options. Budget under 2,000 EUR total.
 No specific timeline."
```

This record is seeded to return an invalid AI response for demo
reproducibility (controlled via `_force_invalid: "bad_category"` in
the test set metadata).

Pipeline trace:
1. Sanitiser: input passes
2. AI Processor: returns `{category: "maybe_value", confidence: 0.78, reason: "Small startup with limited budget."}`
3. Validator: `"maybe_value"` not in `{"high_value", "low_value", "unknown"}` → **validation failure**
4. Fallback Stage 1: retry with strict prompt → same invalid response returned
5. Fallback Stage 2: retry fails → safe default assigned:
   `{category: "unknown", confidence: 0.0, reason: "System default — AI output failed validation after retry."}`
6. Router: `fallback_action == MANUAL_REVIEW_FLAGGED` → `manual_review` (checked before category)
7. Notify: alert written to `data/alerts.json`; Slack/email dispatched if configured
8. SQLite: decision persisted with `fallback_action: manual_review_flagged` and `validation_passed: 0`

Result: `manual_review`. No invalid output reached operations. Failure is visible, logged, and alerted.

---

## 10. Notifications and Downstream Actions

**When a case routes to manual_review:**
1. An alert is written to `data/alerts.json` (always — no config required)
2. A Slack webhook POST is sent (if `SLACK_ENABLED=true` and `SLACK_WEBHOOK_URL` set)
3. An HTML email is sent via Gmail SMTP (if `EMAIL_ENABLED=true` and credentials set)

**Where Slack and email are handled:** `utils/notifier.py` — `notify_manual_review()` calls `_send_slack()` and `_send_email()`. Channel failures are caught and logged — they do not halt the pipeline.

**Where Google Sheets writing is handled:** `utils/sheets.py` — `write_result()` is the single entry point called from `main.py`. It calls:
- `write_to_action_queue()` — inserts at row 2 (newest on top), flags repeat leads
- `append_to_history()` — appends to "Sales History", "Review History", or "Archive" tab based on `final_decision`

**Four Sheets tabs** (source: `utils/sheets.py` line 55):
- `Action Queue` — live CRM working list, all decisions, newest at top
- `Sales History` — append-only, `send_to_sales` decisions
- `Review History` — append-only, `manual_review` decisions
- `Archive` — append-only, `archive` decisions

**Limitations of these integrations:**
- Sheets integration is disabled when `GOOGLE_SHEETS_ID` is blank — the pipeline runs without it
- No batch write or backoff — large runs may hit Google Sheets API rate limits
- Slack and email failures are swallowed (logged, not raised) — a misconfigured webhook won't surface as an error until you check the logs
- `credentials.json` must exist locally and is gitignored — no managed secrets system

---

## 11. Storage and Audit Trail

**Where decisions are stored:** `data/pipeline.db` — SQLite database, created automatically on first run.

**Database layer:** `utils/database.py` — `init_db()` creates the table and indexes, `save_result()` writes each record, `get_recent_decisions()` and `get_lead_history()` support the API read endpoints.

**Table:** `pipeline_results`

**Columns written per record:** `lead_id`, `run_id`, `raw_text`, `received_at`, `category`, `confidence`, `reason`, `validation_passed` (0/1), `fallback_action`, `final_decision`, `processing_ms`, `notes`, `created_at`

**Indexes:** `lead_id`, `run_id`, `final_decision`

**What the audit trail lets you reconstruct:**
- Every decision made in any pipeline run, with the exact AI output, validation result, and fallback action
- Full history of any individual lead across multiple submissions (`GET /audit/{lead_id}`)
- Aggregate statistics across all runs (`GET /stats`)

**How run ID supports traceability:** `generate_run_id()` in `utils/database.py` creates a unique ID per pipeline invocation (format: `run_YYYYMMDD_HHMMSS_<6hex>`). All records in one CLI run or one batch API call share the same run ID, so you can filter by run to see exactly what one execution produced.

---

## 12. Tests and Evidence

**Automated tests:** None. There is no `tests/` directory and no pytest files in this repository. This is a documented gap.

**What substitutes for automated tests:**

The 51-record simulation in `data/sample_input.json` functions as a manual integration test. It covers:
- 15 clean high-value leads (expected: `send_to_sales`)
- 10 clean low-value leads (expected: `archive`)
- 5 ambiguous/unknown leads (expected: `manual_review`)
- 5 high-value below confidence threshold (expected: `manual_review`)
- 3 forced validation failures (expected: fallback → `manual_review`)
- 3 sanitiser-rejected inputs (expected: no AI call, no routing)
- Edge cases: gibberish, HTML injection, German input, long input, repeat lead submission

The `FORCED_FAILURES` dict in `pipeline/ai_processor.py` demonstrates that:
- Invalid category is caught and handled
- Out-of-range confidence is caught and handled
- Empty reason field is caught and handled

**README claims supported by the simulation:**
- "Zero invalid AI outputs reached downstream systems" — structurally guaranteed by Pydantic validation + fallback safe default
- "Every failure routed to a safe handling path" — router's `MANUAL_REVIEW_FLAGGED` branch fires first
- "Fallback triggered on 3 records" — confirmed by code analysis (input_handler.py moves `_force_invalid` into metadata)

**Claims that need stronger automated tests:**
- The fallback count claim (3 records) should be a pytest assertion, not just code analysis
- The routing table should have unit tests for every branch
- The sanitiser should have parametric tests for every rejection case

**The 5–8 most important pytest tests to add:**

1. `test_validator_rejects_invalid_category` — assert `validate()` returns `valid=False` for category `"maybe_value"`
2. `test_validator_rejects_out_of_range_confidence` — assert `valid=False` for confidence `1.85` and `-0.3`
3. `test_validator_rejects_empty_reason` — assert `valid=False` for `reason=""`
4. `test_fallback_assigns_safe_default_after_retry_failure` — mock `ai_processor.process_record` to always return invalid; assert `MANUAL_REVIEW_FLAGGED` and safe default values
5. `test_router_sends_to_sales_above_threshold` — assert `send_to_sales` for `high_value` at `confidence=0.60`
6. `test_router_manual_review_below_threshold` — assert `manual_review` for `high_value` at `confidence=0.59`
7. `test_router_fallback_flag_takes_priority` — assert `manual_review` when `MANUAL_REVIEW_FLAGGED` regardless of category
8. `test_sanitiser_rejects_short_input` — assert `sanitise("Hi", "test")` returns `None`

---

## 13. What Is Not Production-Ready

**API authentication:** All endpoints are open. Anyone who can reach the server can POST leads, read the audit trail, or acknowledge alerts. File: `api.py` — no auth middleware is present.

**SQLite concurrency:** SQLite supports one writer at a time. Under concurrent API load (multiple simultaneous `POST /qualify` calls), writes will queue or fail. File: `utils/database.py`. Production requires PostgreSQL with a connection pool.

**Google Sheets rate limits:** `utils/sheets.py` makes one or two API calls per record (`insert_row` + `append_row`). Large batches will hit Google's per-minute quota. There is no retry or backoff in the Sheets layer.

**Retry and backoff:** `MAX_RETRIES = 1` in `pipeline/fallback.py`. One retry, no delay, no exponential backoff. A transient API failure with no retry grace period will immediately fall through to the safe default and trigger a manual review alert.

**Monitoring and observability:** No structured logging export, no metrics endpoint beyond `GET /stats`, no alerting on validation failure rate spikes. You have to query the API or SQLite directly to see what is happening.

**Secrets and environment:** `.env` file with plaintext credentials. `credentials.json` sits on the local filesystem. No secrets manager, no rotation policy, no per-environment configuration.

**Real deployment concerns:**
- No `Dockerfile` or deployment config
- No process manager (gunicorn, supervisor)
- No TLS — the API runs plain HTTP
- `data/` directory holds the database and alerts file locally — no backup, no replication
- Model version: `gpt-4o-mini` without a snapshot version pin may produce different outputs after a model update

---

## 14. Production Upgrade Path

**1. API authentication**
Add an API key header check as FastAPI middleware (`api.py`). This is a one-file change and should be the first thing done before any deployment.

**2. PostgreSQL**
Replace SQLite with PostgreSQL. Change `utils/database.py` to use `psycopg2` or `asyncpg`. SQLAlchemy or a lightweight ORM would help with connection pooling. `data/pipeline.db` is gitignored so migration is a clean switch.

**3. Exponential backoff and async task queue**
Replace the single synchronous retry in `pipeline/fallback.py` with a configurable backoff strategy. For high volume, move AI calls to an async task queue (Celery + Redis, or similar) so the API returns immediately and processing happens in the background.

**4. Stronger automated tests**
Add pytest with at least the 8 tests listed in section 12. Add a CI step (GitHub Actions) that runs tests on every push. The simulation in `data/sample_input.json` can become a parametric integration test.

**5. Monitoring and alerting**
Export structured logs (JSON format) to a log aggregator. Add a `/metrics` endpoint or Prometheus scraping. Set up alerting on: validation failure rate above X%, fallback rate above Y%, Sheets write errors.

**6. Deployment hardening**
Run behind gunicorn with uvicorn workers. Add TLS (nginx reverse proxy or a managed platform). Containerise with Docker. Move `data/` to a persistent volume. Use a secrets manager (AWS Secrets Manager, Vault) instead of `.env` files.

**7. Real CRM and input source**
Replace `data/sample_input.json` with a webhook receiver (Typeform, HubSpot, or a custom inbound endpoint). Replace Google Sheets with a proper CRM API write (HubSpot, Salesforce). The pipeline already receives JSON via `POST /qualify` — connecting a real source is an infrastructure change, not a code change.

---

## 15. Interview Answers

**"What is the entry point?"**

There are two. For the CLI, it is `main.py` — run `python main.py` and it processes the full 51-record test set end to end. For the API, it is `api.py` — run `uvicorn api:app` and submit leads via `POST /qualify` or `POST /qualify/batch`. Both run the same pipeline logic.

**"What data comes in?"**

A JSON record with three fields: an ID, a raw text field containing the lead content, and optional metadata like source and region. The system accepts this either as a file for the CLI or as an HTTP request body for the API. The raw text is unstructured — it could be a form submission, a CRM note, or anything a human typed.

**"Where is it validated?"**

In two places. First, `utils/sanitiser.py` cleans and rejects the raw text before it ever reaches the AI — it strips HTML, removes control characters, and rejects anything too short or empty. Second, after the AI responds, `pipeline/validator.py` checks that the output has a valid category, a confidence score in range, and a non-empty reason. If either check fails, the pipeline handles it before anything reaches a downstream system.

**"Where does the model get called?"**

In `pipeline/ai_processor.py`, in the `call_openai()` function. If an API key is present, it calls the OpenAI API with `gpt-4o-mini` and requests a structured JSON response. If no key is present, it falls back to `_simulate()`, which returns pre-seeded responses from a dictionary — so the full pipeline runs without a key.

**"What happens if the model fails?"**

The validator catches it. If the model returns an invalid category, an out-of-range confidence score, or an empty reason, validation fails and `pipeline/fallback.py` takes over. It retries once with a stricter prompt. If the retry also fails, the system assigns a safe default — `category="unknown", confidence=0.0` — and flags the record as `MANUAL_REVIEW_FLAGGED`. That flag routes it to human review. Nothing invalid ever reaches operations.

**"Where is the decision stored?"**

In `data/pipeline.db`, a SQLite database managed by `utils/database.py`. Every record gets a row with the lead ID, run ID, AI output, validation result, fallback action, final decision, and processing time. The API exposes this via `GET /audit` and `GET /audit/{lead_id}`. Run ID ties all decisions from one pipeline execution together.

**"What tests prove this works?"**

Honestly, there are no automated tests in this repository. What exists is a 51-record simulation in `data/sample_input.json` that covers every failure mode, including three records seeded to return invalid AI output. When you run `python main.py`, the pipeline processes all of them, the validator catches the invalid ones, the fallback fires, and the results are persisted. The `evals/EVAL_RESULTS.md` documents what should be observed. The next step I would take is adding pytest unit tests for the validator, fallback, and router — the 8 most important tests are listed in the Technical Ownership Sheet.

**"What is not production-ready?"**

Four main things. No API authentication — the endpoints are open. SQLite — it does not handle concurrent writes, which means it would fail under real API load. Single retry with no backoff — a transient model failure immediately escalates to manual review rather than waiting and retrying. And no monitoring — there is no alerting if the validation failure rate spikes. All of these are documented in the README and the production upgrade path is explicit.

---

## 16. Code Ownership Map

| Area | File(s) | Responsibility | What to understand as owner | Interview risk if you cannot explain it |
|---|---|---|---|---|
| Entry point (CLI) | `main.py` | Orchestrates all 8 stages, writes results to JSON | The run ID is generated here; stages called in order; summary printed at end | High — it is the first file a reviewer opens |
| Entry point (API) | `api.py` | FastAPI endpoints, request/response models, calls same pipeline logic as CLI | Which endpoints trigger the pipeline vs. which are read-only | High — API design shows production thinking |
| Input loading | `pipeline/input_handler.py` | Loads JSON, moves `_force_invalid` and `_target_confidence` into metadata | Why `_force_invalid` must be in metadata for the simulator to read it | Medium — comes up when explaining simulation mode |
| Input sanitisation | `utils/sanitiser.py` | Strips HTML, rejects short/empty inputs, truncates at 2000 chars | Rejection rules and what happens to records that fail | Medium — explains why some records never reach the AI |
| Data models | `models/schemas.py` | Pydantic v2 schemas for all pipeline objects | Every enum value, every field — these are what validation checks against | High — schema errors are the most common interview trap |
| AI processor | `pipeline/ai_processor.py` | OpenAI call, simulation mode, strict prompt | How `_simulate()` is selected, what `FORCED_FAILURES` does | High — simulation mode is the first thing demoed |
| Validator | `pipeline/validator.py` | Three-rule validation of AI output | Exact rules, what `None` input produces, where errors go | High — this is the core of the system's claim |
| Fallback | `pipeline/fallback.py` | Retry + safe default assignment | `MAX_RETRIES`, `DEFAULT_SAFE_OUTPUT` values, `FallbackAction` enum | High — fallback is the answer to "what if the AI fails" |
| Router | `pipeline/router.py` | Deterministic rule table | Rule priority order (fallback flag checked first), threshold read from config | High — routing is the operational decision |
| Notifier | `utils/notifier.py` | Slack webhook, email, alerts queue | Always writes to `data/alerts.json`; channel failures are swallowed | Medium — important for human-in-the-loop explanation |
| Sheets | `utils/sheets.py` | 4-tab Sheets CRM write | Tab names, repeat lead detection, which fields are never written by pipeline | Medium — shows operational integration thinking |
| Database | `utils/database.py` | SQLite schema, save, query, stats | Column names, run ID format, index columns, `test_connection()` for health check | Medium — audit trail questions come up |
| Config | `config/settings.py` | All env vars with defaults, `simulation_mode()`, `sheets_enabled()` | Where threshold comes from, how simulation mode is detected | Medium — shows you understand configuration separation |

---

## 17. Self-Review Checklist

Use this before any interview or technical review session.

- [ ] I can explain the full pipeline (all 8 stages) without notes
- [ ] I can name the CLI entry point file and the command to run it
- [ ] I can name the API entry point file and which two endpoints run the full pipeline
- [ ] I can locate the model call (`pipeline/ai_processor.py` → `call_openai()`)
- [ ] I can explain simulation mode and why it works without an API key
- [ ] I can name all three validation rules and their source file (`pipeline/validator.py`)
- [ ] I can explain what happens when validation fails, step by step (`pipeline/fallback.py`)
- [ ] I can state the safe default values assigned after retry failure
- [ ] I can explain the routing table rule order, including why fallback is checked first (`pipeline/router.py`)
- [ ] I can explain why `manual_review` is triggered for low-confidence `high_value` leads
- [ ] I can explain where the confidence threshold comes from and how to change it
- [ ] I can name all four Google Sheets tabs and what each receives (`utils/sheets.py`)
- [ ] I can explain how `data/alerts.json` is written and what it contains (`utils/notifier.py`)
- [ ] I can explain what is stored in SQLite and how run ID supports traceability (`utils/database.py`)
- [ ] I can honestly state that there are no automated tests and name the 5 most important ones to add
- [ ] I can name the four main production gaps without prompting
- [ ] I can give the production upgrade sequence in order
- [ ] I can answer all 8 interview questions in section 15 conversationally

---

## 18. Known Technical Gaps

These gaps were identified by cross-checking code against documentation during
the writing of this document. Recorded here so they are not lost between sessions.

**Gap 1 — README Sheets tab naming mismatch**
README (Key Design Decisions section) listed the four Sheets tabs as:
"Action Queue, Sales, Review, Archive."
The actual tab names in `utils/sheets.py` line 55 are:
`"Action Queue"`, `"Sales History"`, `"Review History"`, `"Archive"`.
The README has been corrected to match the code. If you create the Sheets
workbook manually, use the exact code names — a mismatched tab name causes
`gspread` to throw a `WorksheetNotFound` error at runtime with no fallback.

**Gap 2 — Notification delivery failures are logged but not retried or dead-lettered**
In `utils/notifier.py`, both `_send_slack()` and `_send_email()` wrap their
entire send logic in a bare `except Exception` that logs the error and returns
silently. If Slack or email delivery fails — misconfigured webhook, SMTP timeout,
wrong credentials — the pipeline continues and no retry is attempted. The alert
still lands in `data/alerts.json`, but the external notification is permanently
lost for that record with no visibility beyond the log line.
Production fix: add retry with backoff, or write failed notifications to a
dead-letter queue for re-dispatch. Minimum: surface delivery failures in
`GET /stats` so the ops team knows alerts are not reaching reviewers.

**Gap 3 — OPENAI_MODEL is configurable but not version-pinned**
`config/settings.py` line 17 sets `OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")`.
`"gpt-4o-mini"` is a floating alias that OpenAI may redirect to a newer snapshot
without notice. If the model's output format or classification behaviour changes,
validation failure rates and routing distributions could shift silently. The
system would catch the failures via the validator, but there would be no signal
that the underlying cause is a model change rather than a data change.
Production fix: pin to a dated snapshot (e.g. `gpt-4o-mini-2024-07-18`) and
treat model version upgrades as explicit changes that require re-running the
test set and reviewing `GET /stats` before promoting to production.
