# Demo Checklist — AI Reliability Engine v2.0

## 1. Demo Purpose

Show that AI output cannot be trusted without a validation and fallback layer, then demonstrate a system that handles exactly that — catching invalid outputs, recovering automatically, routing uncertain cases for human review, and leaving a full audit trail.

## 2. Target Audience

- Hiring managers and technical recruiters evaluating AI systems competency
- Technical reviewers assessing production readiness and engineering judgment
- Operations stakeholders who want to understand how AI is made safe for business workflows

## 3. Expected Duration

10–15 minutes including questions. Core pipeline run: under 2 minutes.

## 4. 60-Second Explanation

> "Most AI workflow demos stop at classification. This one handles what happens when the AI is wrong.
>
> The system sits between an AI classifier and your operational systems. Every AI response gets validated against a strict schema — correct category, confidence in range, reason present. If it fails, the system retries with a stricter prompt. If it fails again, it assigns a safe default and flags the lead for manual review. Nothing invalid ever reaches a downstream action.
>
> I ran this on 51 test records, including records deliberately engineered to trigger every failure mode. Zero invalid outputs reached operations. Every decision is in the audit database."

## 5. Demo Flow

### Step 1 — Explain the problem (2 min)

Open the README. Point to **The Problem With AI in Operations** and **Why Not Just Use Rules?**

Key point to land: AI is probabilistic. It returns wrong categories, out-of-range confidence scores, empty fields. Downstream systems don't self-heal. A validation layer is not optional — it's the difference between a demo and something you can run in production.

### Step 2 — Show normal successful processing (3 min)

Run:
```bash
python main.py
```

Walk through the console output for a clean high-value lead (`lead_001`):
- Input loaded and sanitised
- AI classified: `high_value`, confidence `0.95`
- Validation passed
- Routed to `send_to_sales`
- Persisted to SQLite

Point out: every step is a logged boundary. Nothing is implicit.

### Step 3 — Show invalid AI output handling (3 min)

Point to `pipeline/ai_processor.py` → `FORCED_FAILURES`. Explain that `lead_037`, `lead_038`, `lead_039` are seeded to return:
- Invalid category (`maybe_value` — not in the allowed enum)
- Out-of-range confidence (`1.85`, `-0.3`)
- Empty required field (`reason: ""`)

Run the pipeline and show the console output for these records. Validator catches each failure. Key line: *"Validation failed — triggering fallback."*

### Step 4 — Show fallback and manual review routing (3 min)

Continue from the same run. Show:
- Fallback retries with a strict prompt
- If retry fails: safe default assigned (`manual_review_flagged`)
- Router maps this to `manual_review`
- Alert dispatched to console + `data/alerts.json`

Open `data/alerts.json`. Show the queued alert with `lead_id`, `reason`, `fallback_action`, and `status: pending`.

If Slack/email is configured: show the notification. If not: explain the configuration in `.env.example`.

Show confidence-threshold manual review separately: `lead_031` (high_value, confidence 0.52 — below 0.60 threshold). Valid output, valid category, but routed to manual review because confidence is too low. This is intentional routing, not a failure.

### Step 5 — Show audit trail (2 min)

Start the API:
```bash
uvicorn api:app --reload --port 8000
```

Hit:
- `GET /audit` — all recent decisions
- `GET /audit/lead_037` — full history for a specific lead across runs
- `GET /alerts` — pending manual review queue
- `GET /stats` — aggregate metrics

Point out: every decision is queryable by lead ID across multiple runs. Run ID is on every record. This is what makes the system auditable, not just functional.

---

## 6. Expected Questions

**"What happens when the AI is wrong?"**

> The validator catches it immediately. If the output fails schema — wrong category, confidence out of 0–1 range, missing reason — the fallback fires: retry with a stricter prompt. If that fails too, the system assigns a safe default and flags the lead for human review. The AI being wrong never causes a silent failure or a wrong decision reaching operations.

**"Why not just trust the AI directly?"**

> Because AI output is probabilistic, not deterministic. Even a well-prompted model returns wrong categories, malformed JSON, and out-of-range values. The validation layer is what makes the difference between a system that works 95% of the time in a demo and one you can run overnight without monitoring. The 51-record test set includes deliberate edge cases specifically to prove this point.

**"Is this production-ready?"**

> The core architecture is — Pydantic v2 at every boundary, structured fallback, SQLite audit trail, configurable threshold, simulation mode. Known limitations are documented: single retry (no exponential backoff), SQLite not suitable for high-concurrency writes, no API authentication on endpoints. The production path is also documented: PostgreSQL, async task queue, API auth, exponential backoff.

---

## 7. Success Criteria

The demo succeeds if the reviewer leaves with three things:

1. **The problem is understood** — they can explain why AI output needs a validation layer, not just a prompt.
2. **The system behaviour is clear** — they saw a failure caught, a fallback fire, and a manual review routed correctly.
3. **The engineering judgment is visible** — they noticed that failure modes are explicit, not handled by silent try/except; that confidence threshold is configurable, not hardcoded; and that every decision is traceable by run ID.

If they ask about the production path, the Known Limitations section answers it. If they ask to see the code, point to `pipeline/validator.py` and `pipeline/fallback.py` first — those are the core of what this system is.
