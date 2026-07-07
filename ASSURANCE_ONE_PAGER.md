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
| Input rejected by sanitiser | Record logged as rejected; no AI call made; routed to `manual_review` via the fallback safe default (decision, DB row, and alert are still produced) |
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
| Google Sheets | 4-tab workbook: Action Queue, Sales History, Review History, Archive; repeat leads detected and flagged in the Action Queue (CLI runs with Sheets credentials only) |
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

---

## Risk Register

Each mitigation below was checked against this repo's code at the audited
HEAD (`ddff88b`), not asserted from design intent. Rows where the code
did not fully back the original claim have the mitigation reworded to
what the code actually does, with the gap stated as residual risk.

| Risk | Likelihood | Impact | Mitigation in this system | Residual risk, stated honestly |
|---|---|---|---|---|
| Invalid AI output enters a business workflow | Medium | High | Schema + rule validation (`pipeline/validator.py` — category enum, 0.0–1.0 confidence range, non-empty reason); retry with strict prompt (`pipeline/fallback.py` — `MAX_RETRIES = 1`); safe-default assignment (`DEFAULT_SAFE_OUTPUT`); always routed to manual review, no exceptions (`pipeline/router.py` — `MANUAL_REVIEW_FLAGGED` check fires first) | Semantically wrong but schema-valid outputs pass — the validator checks form, not truth |
| Silent degradation when API key is missing/placeholder | Medium | High | **Partially unmitigated.** `config.simulation_mode()` (`config/settings.py:41-42`) is a truthiness check on `OPENAI_API_KEY` — it correctly detects a *missing* key, but `.env.example`'s non-empty placeholder (`your_openai_api_key_here`) would **not** be detected: `pipeline/ai_processor.py:128-156` takes the live-call path, the 401 is caught by a generic `except Exception`, and the record returns `None` → the same fallback/manual_review path as a genuine AI failure. This exact pattern (placeholder key silently defeating simulation-mode detection) was found and code-fixed in three sibling engines — Decision (`f9d3230`, `1449b44`), Execution (`a5a9725`), Context (`eefeeb8`) — per `kristian-os/domains/github-ops/STATE.md:100,118`. This repo is not on that list: its own audit predates the pattern's discovery by one day and was never re-checked against it. Current mitigation is operational only (demo runs with no `.env` present), not code | Misconfiguration is silently indistinguishable from a genuine AI validation failure in this repo specifically — an operator cannot tell "the model got it wrong" from "the model was never actually called" without reading logs line-by-line |
| Partial run with no failure marker (crash mid-run, records already persisted) | Low (post-fix) | High | The original crash vector (B1: Windows cp1252 console encoding) is fixed — `utils/logger.py` reconfigures `stdout`/`stderr` to UTF-8 with `errors="replace"` at import time (commit `8439955`), so logging can no longer raise mid-run. **No explicit persisted-state reconciliation or exit-code assertion exists** — `main.py`/`api.py` contain no `sys.exit()` call; "exit code 0" is only the Python default when nothing raises, not a checked invariant | Hard kills (power, OOM) can still strand state between checkpoints; run completeness is currently verified by eye against the printed summary count, not by an automated reconciliation check |
| Encoding crash on non-ASCII input (Windows cp1252 console) | Low (post-fix) | Medium | Console streams reconfigured to UTF-8 with replacement at logger import (`utils/logger.py`, commit `8439955`); DB persistence (`utils/database.py`) uses stdlib `sqlite3` with plain `TEXT` columns — no lossy encoding step before storage, confirmed by inspection | New print paths added later can reintroduce the class if they write to a stream before `utils.logger` has been imported and reconfigured it |
| Downstream write fails after decision made (Sheets/Slack/email) | Medium | Medium | SQLite `save_result()` and the local `alerts.json` queue are written before Slack/email are attempted (`main.py` call order; `utils/notifier.py` wraps `_send_slack`/`_send_email` each in their own `try/except`, logging failure without blocking the DB write or the other channel) | No automated retry on a failed Slack/email send — partial delivery window persists until a human notices or the next run happens to re-trigger it |
| Spreadsheet formula injection via USER_ENTERED writes | Low | Medium | Fixed (M2, commit `8439955`): `utils/sheets.py:112,190` write with `value_input_option="RAW"` explicitly, with an inline comment recording why ("never let lead-supplied text be evaluated as a spreadsheet formula") | No test in the repo (there are no automated tests at all — confirmed, `find` returns none) enforces this stays `RAW`; one future code change reopens it silently |
| Cost/quota runaway on retry loops | Low | Medium | Bounded retry count confirmed (`pipeline/fallback.py:11`, `MAX_RETRIES = 1`); simulation mode (`config.simulation_mode()`) makes dev iteration free of API calls | No hard spend ceiling anywhere in this codebase (grep confirms no budget/cost-ceiling logic) — platform-side (API account) risk only |
| Prompt injection via input record content | Medium | Medium | Input sanitisation in `utils/sanitiser.py`: script/style block removal now runs **before** generic tag stripping (fixed — the reverse order was M2, dead code prior to `8439955`), control characters stripped, sub-5-char inputs rejected, over-2000-char inputs truncated | Adversarial plain-text instructions inside otherwise legitimate-looking fields are not HTML and are not detectable by sanitisation, which only strips markup/control characters/length — it does not inspect semantic content |
| Validation thresholds go stale vs reality | Medium | Medium | `CONFIDENCE_THRESHOLD` centralized in `config/settings.py:36` (env var, default `0.60`), read in one place (`pipeline/router.py`). Outcome feedback is confirmed to exist in the sibling Decision engine (a dedicated outcome feedback loop, per `kristian-os` portfolio state) and outcome-based impact scoring exists in the sibling Impact engine — neither recalibrates this repo's threshold; not enforced here | No automated recalibration in this repo — a threshold set at launch stays fixed until someone manually revisits `config/settings.py`; staleness is invisible until outcomes drift |


