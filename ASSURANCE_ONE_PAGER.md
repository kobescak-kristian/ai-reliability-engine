# AI Assurance One-Pager — AI Reliability Engine v2.0

> For hiring managers, technical reviewers, and AI Operations roles
> evaluating how AI risk is managed in this system.

---

## System Purpose

Validates and routes AI-classified leads before any output reaches
an operational system (sales CRM, Google Sheets, human review queue).
Catches invalid AI output, applies structured fallback, and logs every
decision with a traceable run ID.

---

## Users / Stakeholders

| Role | Interaction |
|---|---|
| Sales operations | Receives `send_to_sales` decisions via Google Sheets Action Queue tab |
| Human reviewers | Receives `manual_review` alerts via Slack webhook or HTML email |
| Operations / AI team | Monitors pipeline via REST API (`/stats`, `/audit`, `/alerts`) and SQLite |
| Hiring / technical reviewers | Reviews this repository to assess AI operations engineering competency |

---

## Data Entering the System

- **Input format:** Unstructured lead text submitted via JSON file (CLI) or
  HTTP request (API)
- **Fields per record:** `id` (string), `raw_text` (string),
  optional `metadata` (source, region, company_size)
- **Sanitisation before AI call:** HTML and script tags stripped, control
  characters removed, inputs under 5 characters rejected, inputs over 2000
  characters truncated (`utils/sanitiser.py`)
- **Privacy note:** Sample data (`data/sample_input.json`) contains no real
  personal information. Production use requires a defined data handling policy —
  none is currently implemented.

---

## AI Role

| Property | Value |
|---|---|
| Model | OpenAI gpt-4o-mini (configurable via `OPENAI_MODEL` env var) |
| Task | Classify lead text into one of three categories |
| Output format required | Structured JSON: `{category, confidence, reason}` |
| Temperature | 0.1 — low, for consistency |
| Non-JSON response | Treated as a validation failure; fallback fires |
| Autonomy level | AI classifies only — a deterministic routing layer makes all operational decisions |

The AI does not take any operational action. It produces a classification
that is validated, then routed by deterministic rules.

---

## Deterministic Controls

| Control | Where implemented |
|---|---|
| Allowed category enum | `pipeline/validator.py` — enum check, not trust |
| Confidence range 0.0–1.0 | `pipeline/validator.py` — rejects < 0.0 or > 1.0 |
| Confidence threshold | `config/settings.py` via `CONFIDENCE_THRESHOLD` env var (default 0.60) — below threshold routes to manual review regardless of category |
| Routing logic | Deterministic rule table in `pipeline/router.py` — no AI involvement |
| Fallback safe default | Constructed in code: `category="unknown", confidence=0.0` — guaranteed valid, always routes to manual_review |
| Input sanitisation | Deterministic string processing in `utils/sanitiser.py` before any AI call |

---

## Human Oversight

- Every `manual_review` decision triggers a Slack webhook + HTML email alert
  (both disabled by default; enabled via `SLACK_ENABLED=true` /
  `EMAIL_ENABLED=true` in `.env`)
- Manual review alerts queued to `data/alerts.json` regardless of
  Slack/email configuration — local queue always written
- Alerts acknowledged via `PATCH /alerts/{lead_id}/acknowledge`
- Low-confidence `high_value` leads (confidence < 0.60) are not auto-actioned
  regardless of category — they route to manual review
- Fallback-flagged records (`MANUAL_REVIEW_FLAGGED`) always go to manual review;
  this check fires before any category-based routing

---

## Failure Handling

| Failure mode | System response |
|---|---|
| Invalid AI category | Validator catches → retry with strict prompt → safe default if retry fails |
| Out-of-range confidence | Validator catches → retry → safe default if retry fails |
| Empty reason field | Validator catches → retry → safe default if retry fails |
| AI returns None or non-JSON | Treated as validation failure (`errors=["AI returned no output"]`) → fallback |
| Input rejected by sanitiser | Record logged as rejected; no AI call made; no routing decision |
| Safe default assigned | Routes to `manual_review` — never auto-actioned |

No failure mode results in a silent pass-through to operations. Every
failure is logged, every fallback-flagged record generates an alert.

---

## Auditability

| Mechanism | Detail |
|---|---|
| SQLite audit trail | Every decision persisted with `run_id`, `lead_id`, `category`, `confidence`, `fallback_action`, `final_decision`, `validation_passed`, `processing_ms`, `notes` |
| Run ID | Every pipeline invocation generates a unique `run_id`; all decisions in that run share it |
| Cross-run lead history | `GET /audit/{lead_id}` returns full decision history for one lead across all runs |
| Alert log | `data/alerts.json` stores all manual review alerts with timestamp, reason, and `status` (pending / acknowledged) |
| Google Sheets | 4-tab workbook: Action Queue, Sales, Review, Archive; repeat leads detected and flagged automatically |
| Aggregate metrics | `GET /stats` returns total processed, decisions by type, fallback count, manual review rate, avg processing time |

---

## Privacy / Data Notes

- Sample data contains no real personal information
- `data/pipeline.db` and `data/alerts.json` are gitignored and never committed
- No authentication on API endpoints — see Production Gaps
- No data retention or deletion policy is defined — required before production use
- `credentials.json` (Google Sheets service account) is gitignored;
  referenced by `GOOGLE_CREDENTIALS_FILE` env var

---

## Production Gaps

| Gap | Status |
|---|---|
| No API authentication | Known — documented in README Known Limitations |
| Single retry, no backoff | Known — `MAX_RETRIES = 1` in `pipeline/fallback.py` |
| SQLite only | Known — not suitable for distributed or concurrent deployment |
| Google Sheets rate limits | Known — large batches may hit API limits without backoff |
| No pipeline health monitoring or alerting | TODO |
| No data retention or deletion policy | TODO |
| No model version pinning | TODO — `gpt-4o-mini` without a snapshot version may drift |
| No input schema versioning | TODO — metadata fields are unvalidated dict |

---

## Risk Rating

| Dimension | Assessment |
|---|---|
| AI autonomy level | Low — AI classifies only; all decisions made by deterministic rules |
| Failure visibility | High — every failure logged, alerted, and persisted |
| Silent failure modes | None by design — fallback catches every unvalidated output |
| Data sensitivity | TODO — depends on production input data |
| Downstream harm if wrong | TODO — depends on what `send_to_sales` triggers in production |
| Overall risk rating | TODO — assess after production context and data sensitivity defined |
