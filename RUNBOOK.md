# Runbook — AI Reliability Engine v2.0

Operational reference for running, diagnosing, and recovering the pipeline.
Written for developers and AI operations roles.

---

## Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env — no values required for simulation mode
# For live mode: set OPENAI_API_KEY
```

Simulation mode runs without any API key. The bundled 51-record test set
produces deterministic results including deliberate edge cases.

---

## 1. Start System (CLI — full pipeline)

```bash
python main.py
```

| Path | Default |
|---|---|
| Input | `data/sample_input.json` |
| Output (JSON) | `data/results.json` |
| Audit database | `data/pipeline.db` (created on first run) |
| Alerts queue | `data/alerts.json` (created on first manual_review alert) |

**Custom paths:**
```bash
python main.py --input path/to/input.json --output path/to/output.json
```

Expected console output on a clean run:
```
[SECTION] AI RELIABILITY ENGINE v2.0 — START
[INFO]    simulation_mode: True
[INFO]    Run ID: run_20260619_143022_abc123
...
[SECTION] PIPELINE SUMMARY
[INFO]    Total records : 51
...
[SUCCESS] Persisted    → data/pipeline.db
[SUCCESS] Alerts queue → data/alerts.json
```

---

## 2. Run CLI Demo

Run the full 51-record test set and observe the validation and fallback layers:

```bash
python main.py
```

**Records that trigger forced validation failures:** lead_037, lead_038, lead_039

Watch for these log lines:
```
[WARNING] [lead_037] Validation error: Invalid category 'maybe_value' — must be one of {'high_value', 'low_value', 'unknown'}
[WARNING] [lead_037] Validation failed — triggering fallback
[WARNING] [lead_037] Fallback Stage 1: retrying with strict prompt
[WARNING] [lead_037] Retry failed — assigning safe default
[WARNING] [lead_037] Fallback Stage 2: safe default assigned, flagged for manual review
[ALERT]   [MANUAL REVIEW] lead=lead_037 | Validation failed after retry — safe default assigned
```

**Records rejected by sanitiser (no AI call):** lead_040 (empty), lead_041
(whitespace-only), lead_050 ("Hi" — too short)

**Records sanitised then classified:** lead_042 (XSS attempt stripped),
lead_048 (HTML tags stripped)

---

## 3. Start API

```bash
uvicorn api:app --reload --port 8000
```

| URL | Purpose |
|---|---|
| http://localhost:8000/docs | Swagger UI — interactive endpoint explorer |
| http://localhost:8000/redoc | Redoc documentation |

The API initialises the SQLite database on startup (`init_db()` is called at
module load). Safe to run alongside a CLI session.

**Submit a single lead:**
```bash
curl -X POST http://localhost:8000/qualify \
  -H "Content-Type: application/json" \
  -d '{"id":"test_01","raw_text":"CFO confirmed 40k EUR budget. CTO and procurement on call. Go-live in 8 weeks."}'
```

**Submit a batch (up to 50 leads):**
```bash
curl -X POST http://localhost:8000/qualify/batch \
  -H "Content-Type: application/json" \
  -d '{"leads":[{"id":"test_01","raw_text":"Enterprise client, confirmed budget, urgent timeline."},{"id":"test_02","raw_text":"Student researching AI tools for a dissertation."}]}'
```

---

## 4. Health Check

```bash
curl http://localhost:8000/health
```

Expected response (simulation mode, no integrations configured):
```json
{
  "status": "ok",
  "database": "connected",
  "simulation_mode": true,
  "slack_enabled": false,
  "email_enabled": false,
  "confidence_threshold": 0.6,
  "version": "2.0.0"
}
```

`"status": "degraded"` means the SQLite database is unreachable. See
Recovery section below.

---

## 5. Common Failures

**Pipeline exits immediately with no records processed**

Verify the input file exists and is valid JSON:
```bash
python -c "import json; json.load(open('data/sample_input.json'))"
```

**`ModuleNotFoundError` on startup**

Dependencies not installed:
```bash
pip install -r requirements.txt
```

**`OPENAI_API_KEY` not set — running in simulation mode**

Expected and intentional when no key is provided. Not an error.
To use the live model, add `OPENAI_API_KEY=...` to `.env`.

**Google Sheets errors on startup**

Sheets integration is disabled when `GOOGLE_SHEETS_ID` is blank.
If you see `gspread` errors, leave `GOOGLE_SHEETS_ID=` empty in `.env`.
`config.sheets_enabled()` returns `False` and the sheets write is skipped
without error.

**Slack / email alerts not sending**

Alerts are always written to `data/alerts.json` regardless of channel
configuration. If Slack or email is not delivering:
1. Check `.env`: `SLACK_ENABLED=true` and `SLACK_WEBHOOK_URL` must both be set
2. Check `.env`: `EMAIL_ENABLED=true`, `EMAIL_SENDER`, `EMAIL_APP_PASSWORD`,
   and `EMAIL_RECIPIENT` must all be set
3. Channel failures are logged as `[ERROR]` and do not halt the pipeline

---

## 6. Diagnose Validation Failures

Validation failures are logged immediately with lead ID and error text:
```
[WARNING] [lead_037] Validation error: Invalid category 'maybe_value' — must be one of {'high_value', 'low_value', 'unknown'}
```

**Inspect all validation failures after a run (SQLite):**
```bash
sqlite3 data/pipeline.db \
  "SELECT lead_id, run_id, category, confidence, fallback_action, notes
   FROM pipeline_results
   WHERE validation_passed = 0;"
```

**Inspect a specific lead's validation history (API):**
```bash
curl http://localhost:8000/audit/lead_037
```

Returns full decision history across all runs for that lead ID, including
`fallback_action` and `notes` (which records the specific validation errors
that triggered the fallback).

**Validation rules (source of truth: `pipeline/validator.py`):**
- `category` must be in `{"high_value", "low_value", "unknown"}`
- `confidence` must be a float in `[0.0, 1.0]`
- `reason` must be a non-empty string after stripping whitespace

---

## 7. Inspect Manual Review Alerts

**Alert file (always written, no configuration required):**
```bash
cat data/alerts.json
```

Structure of each alert:
```json
{
  "lead_id": "lead_037",
  "run_id": "run_20260619_143022_abc123",
  "reason": "Validation failed after retry — safe default assigned",
  "fallback_action": "manual_review_flagged",
  "validation_errors": ["Invalid category 'maybe_value' — must be one of {'high_value', 'low_value', 'unknown'}"],
  "status": "pending",
  "created_at": "2026-06-19T14:30:25.123456+00:00"
}
```

**Via API — pending alerts only (default):**
```bash
curl http://localhost:8000/alerts
```

**Via API — full history including acknowledged:**
```bash
curl "http://localhost:8000/alerts?status=all"
```

**Acknowledge an alert (mark as reviewed):**
```bash
curl -X PATCH http://localhost:8000/alerts/lead_037/acknowledge
```

Sets `"status": "acknowledged"` and adds `"acknowledged_at"` timestamp
in `data/alerts.json`.

---

## 8. Inspect Audit Logs

**Recent 20 decisions (API):**
```bash
curl http://localhost:8000/audit
```

**Recent 50 decisions:**
```bash
curl "http://localhost:8000/audit?limit=50"
```

**Full history for a specific lead across all runs:**
```bash
curl http://localhost:8000/audit/lead_001
```

**Aggregate pipeline statistics:**
```bash
curl http://localhost:8000/stats
```

Returns: `total_processed`, `total_runs`, `decisions` (count by type),
`fallbacks_triggered`, `avg_processing_ms`, `manual_review_rate`.

**Direct SQLite queries:**
```bash
# Most recent decisions
sqlite3 data/pipeline.db \
  "SELECT lead_id, run_id, final_decision, fallback_action, created_at
   FROM pipeline_results
   ORDER BY created_at DESC LIMIT 20;"

# All manual review decisions
sqlite3 data/pipeline.db \
  "SELECT lead_id, run_id, fallback_action, notes, created_at
   FROM pipeline_results
   WHERE final_decision = 'manual_review'
   ORDER BY created_at DESC;"

# Fallback rate by run
sqlite3 data/pipeline.db \
  "SELECT run_id, COUNT(*) as total,
     SUM(CASE WHEN fallback_action != 'none' THEN 1 ELSE 0 END) as fallbacks
   FROM pipeline_results
   GROUP BY run_id;"
```

Table: `pipeline_results`
Columns: `id, lead_id, run_id, raw_text, received_at, category, confidence,
reason, validation_passed, fallback_action, final_decision, processing_ms,
notes, created_at`
Indexes: `lead_id`, `run_id`, `final_decision`

---

## 9. Recovery Steps

**Database corrupted or missing**

Delete and let the system reinitialise:
```bash
rm data/pipeline.db
python main.py   # init_db() runs on startup and recreates all tables and indexes
```

Prior run history is lost. If the file exists but is locked by a hung
process, identify and stop that process before deleting.

**Alerts file corrupted**

Reset to an empty queue:
```bash
echo [] > data/alerts.json
```

On Windows PowerShell:
```powershell
Set-Content data/alerts.json "[]" -Encoding utf8
```

Prior alerts in Slack or email are still visible. The file is the local
queue only — the SQLite audit trail is unaffected.

**Port 8000 already in use**

```bash
uvicorn api:app --reload --port 8080
```

Or identify the process holding port 8000:
```bash
# Linux / Mac
lsof -i :8000

# Windows
netstat -ano | findstr :8000
```

**`data/` directory missing**

The pipeline creates `data/` automatically via `mkdir(exist_ok=True)` in
`utils/database.py` and `utils/notifier.py`. If it's missing and the CLI
still fails, check filesystem permissions.

---

## 10. Escalation / Production Notes

This system runs as a single process backed by SQLite. For production deployment:

| Current | Production upgrade |
|---|---|
| SQLite (`data/pipeline.db`) | PostgreSQL — required for concurrent writers |
| `data/alerts.json` local queue | Database-backed alert queue with persistent status |
| No API authentication | Auth middleware (API key or OAuth) required before exposing endpoints |
| MAX_RETRIES = 1 in `pipeline/fallback.py` | Exponential backoff with dead-letter queue for records exhausting retries |
| `gpt-4o-mini` without version pin | Pin to a specific model snapshot to prevent silent drift |
| No pipeline health monitoring | Structured log export + alerting on validation failure rate spike |

Production path is documented in the README Known Limitations section.

For issues not covered here, the primary diagnostic files are:
- `pipeline/validator.py` — validation rules and error messages
- `pipeline/fallback.py` — retry logic and safe default assignment
- `utils/database.py` — schema, queries, and indexes
- `utils/notifier.py` — alert queue write logic
