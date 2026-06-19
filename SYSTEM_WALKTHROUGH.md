# System Walkthrough — AI Reliability Engine v2.0

A self-contained reviewer document. Written for hiring managers, technical
reviewers, and AI Operations roles evaluating this project without a
live demo.

---

## Purpose of This Document

This walkthrough explains what the system does, why it exists, how it
handles both successful and failed AI output, and what that demonstrates
about AI operations engineering. It is self-contained — you do not need
to run the code to understand the system.

Supporting files are linked at the bottom for deeper review.

---

## The Problem This System Solves

AI classification is probabilistic. A well-prompted model still returns:
- Wrong category values not in the allowed set
- Confidence scores outside the valid 0.0–1.0 range
- Empty required fields
- Non-JSON responses or call failures

Downstream operational systems — sales CRMs, support queues, routing
workflows — do not self-validate. If an invalid AI output reaches them,
the result is a wrong routing decision, a silent error, or undefined
behaviour. There is no natural catch point.

Most AI workflow demos stop at classification and assume the model is
correct. This system handles what happens when it is not.

---

## What the System Does

A validation and fallback layer that sits between an AI classifier and
operational systems. Every AI response is validated before any routing
decision is made. Every failure is handled explicitly. Every decision
is logged with a traceable run ID.

**Use case:** Inbound lead qualification for a B2B SaaS context. Leads
arrive as unstructured text. The AI classifies each one. This system
validates that classification, decides what to do with it, and routes
it to the correct downstream action — without ever letting an invalid
output through.

**Who it is for:** Teams using AI in operational workflows — sales
automation, CRM enrichment, support routing, document processing —
where invalid AI output has a real operational cost.

---

## Why Validation Is Needed Before Routing

The routing table is deterministic:

| Condition | Decision |
|---|---|
| `high_value` + confidence ≥ 0.60 | `send_to_sales` |
| `high_value` + confidence < 0.60 | `manual_review` |
| `low_value` | `archive` |
| `unknown` category or fallback triggered | `manual_review` |

This only works safely if the inputs are valid. An out-of-range confidence
value (`1.85`) would pass the threshold check and auto-action a lead that
should be reviewed. An invalid category (`"maybe_value"`) has no defined
routing path. A missing reason field means the decision cannot be explained
or audited.

Validation is not defensive programming — it is the mechanism that makes
deterministic routing on probabilistic AI output possible. See
[adr/001-validation-before-routing.md](adr/001-validation-before-routing.md)
for the full decision record.

---

## Architecture — 8-Stage Pipeline

```
Input JSON / API request
        │
        ▼
┌─────────────────┐
│  Input Handler  │  Load records; move control metadata into record
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Sanitiser     │  Strip HTML, reject empty / too-short / whitespace-only
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI Processor   │  OpenAI gpt-4o-mini → structured JSON output
│                 │  (simulation mode available without API key)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Validator     │  category ∈ {high_value, low_value, unknown}
│                 │  confidence ∈ [0.0, 1.0]
│                 │  reason non-empty
└────────┬────────┘
         │         │
    PASS │    FAIL │
         │         ▼
         │  ┌─────────────────┐
         │  │    Fallback     │  Retry with strict prompt (MAX_RETRIES=1)
         │  │                 │  If retry fails → safe default assigned
         │  └────────┬────────┘
         │           │
         └─────┬─────┘
               ▼
┌─────────────────┐
│     Router      │  Deterministic rule table → final decision
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Notify  │  Sheets  │  Persist       │
│  Slack + │  4-tab   │  SQLite with   │
│  email   │  CRM     │  run ID        │
└──────────────────────────────────────┘
```

All pipeline boundaries use Pydantic v2 schema validation. Silent
pass-through between stages is structurally impossible.

---

## Happy Path Example

**Input:** `lead_001`
```
"Enterprise client requested a demo of our full platform.
 Budget confirmed at 50,000 EUR annually.
 CFO and CTO both attending the call."
```

**Pipeline trace:**
1. Sanitiser: input is clean, no transformation needed
2. AI Processor: returns `{category: "high_value", confidence: 0.95, reason: "Enterprise demo with confirmed 50k EUR annual budget and C-suite attendance."}`
3. Validator: all fields valid — passes
4. Router: `high_value` + `confidence 0.95 ≥ 0.60` → `send_to_sales`
5. Notify: no alert (not `manual_review`)
6. Google Sheets: written to Action Queue tab and Sales tab
7. SQLite: decision persisted with run ID

**Result:** `send_to_sales`. No human intervention required. Decision traceable by lead ID.

---

## Failure Path Example

**Input:** `lead_037`
```
"Small startup exploring options. Budget under 2,000 EUR total.
 No specific timeline."
```

This record is seeded to return an invalid AI response for demo
reproducibility (controlled via `_force_invalid: "bad_category"` in
the test set metadata).

**Pipeline trace:**
1. Sanitiser: input passes
2. AI Processor: returns `{category: "maybe_value", confidence: 0.78, reason: "Small startup with limited budget."}`
3. Validator: `"maybe_value"` not in `{"high_value", "low_value", "unknown"}` → **validation failure**
4. Fallback Stage 1: retry with strict prompt → same invalid response returned
5. Fallback Stage 2: retry fails → safe default assigned:
   `{category: "unknown", confidence: 0.0, reason: "System default — AI output failed validation after retry."}`
6. Router: `fallback_action == MANUAL_REVIEW_FLAGGED` → `manual_review` (checked before category)
7. Notify: alert written to `data/alerts.json`; Slack/email dispatched if configured
8. SQLite: decision persisted with `fallback_action: manual_review_flagged` and `validation_passed: 0`

**Result:** `manual_review`. No invalid output reached operations. Failure is visible, logged, and alerted.

---

## Fallback and Manual Review Behaviour

**Fallback sequence** (`pipeline/fallback.py`):

1. Validation fails → retry with a stricter system prompt (one retry, `MAX_RETRIES = 1`)
2. Retry passes → `FallbackAction.RETRY`, routes normally
3. Retry also fails → safe default assigned (`category="unknown", confidence=0.0`) → `FallbackAction.MANUAL_REVIEW_FLAGGED`

The safe default is constructed in code, not by the model. It is
guaranteed to pass validation and always routes to `manual_review`.

**Manual review is also triggered without a fallback** when the AI
output is valid but the confidence is too low:
- `high_value` + confidence < 0.60 → `manual_review`
- Example: `lead_031` — AI correctly classifies as `high_value` with
  confidence `0.52`. Valid output, but not confident enough to auto-action.

**Threshold is configurable:** `CONFIDENCE_THRESHOLD` is an environment
variable (default `0.60`). Changing it requires no code modification.

**In the 51-record test set:**
- 3 records trigger fallback and exhaust retry (lead_037, lead_038, lead_039)
- 5 records are `high_value` below the confidence threshold (lead_031–035)
- All `unknown` category records route to `manual_review`
- 3 records are rejected by the sanitiser before reaching the AI (lead_040, lead_041, lead_050)

---

## Auditability and Traceability

Every decision is persisted to SQLite (`data/pipeline.db`) with:

| Field | Purpose |
|---|---|
| `lead_id` | Identifies the record |
| `run_id` | Ties all decisions in one pipeline run together |
| `category` | What the AI returned |
| `confidence` | AI confidence score |
| `validation_passed` | Whether the AI output passed schema validation |
| `fallback_action` | `none`, `retry`, or `manual_review_flagged` |
| `final_decision` | `send_to_sales`, `archive`, or `manual_review` |
| `notes` | Validation errors that triggered fallback, if any |
| `processing_ms` | Per-record processing time |

**Queryable via REST API:**
- `GET /audit` — recent decisions
- `GET /audit/{lead_id}` — full history for one lead across all runs
- `GET /alerts` — pending manual review queue
- `GET /stats` — aggregate metrics (total, by decision type, fallback rate, avg time)

Manual review alerts are also written to `data/alerts.json` with
`status: pending` and acknowledged via `PATCH /alerts/{lead_id}/acknowledge`.

---

## What This Demonstrates for AI Operations Roles

**1. The validation layer is not an afterthought.**
It is the architecture. Nothing flows between pipeline stages without
passing a schema boundary. Pydantic v2 enforces this structurally —
there is no way to introduce a silent pass-through without changing the
schema models.

**2. Failure modes are explicit and enumerated.**
The test set includes records seeded to trigger every known failure mode:
invalid category, out-of-range confidence, empty required field,
whitespace-only input, HTML injection, gibberish, inputs too short to
classify, and borderline-confidence cases. Each is handled by a named
code path, not a catch-all exception handler.

**3. Uncertainty is routed, not suppressed.**
Low-confidence outputs that pass validation are not auto-actioned.
They route to `manual_review`. The confidence threshold is a
runtime-configurable parameter, not a hardcoded constant, because the
right threshold depends on deployment context.

**4. Every decision is traceable.**
Run ID on every record means you can reconstruct any pipeline run.
Lead ID indexing means you can see how a specific lead was handled
across multiple submissions. The audit trail exists before production
is a consideration.

**5. Production gaps are documented, not hidden.**
Known limitations are in the README, ASSURANCE_ONE_PAGER.md, and
ADR-001. The production path is explicit: PostgreSQL, exponential
backoff, API authentication, model version pinning. Documenting what
is missing is part of engineering judgment.

---

## Known Limitations / Production Path

| Current | Production upgrade |
|---|---|
| SQLite | PostgreSQL — required for concurrent writers |
| Single retry, no backoff | Exponential backoff with dead-letter queue |
| No API authentication | Auth middleware required before exposing endpoints |
| `gpt-4o-mini` without version pin | Pin to a specific model snapshot |
| `MAX_RETRIES = 1` in `pipeline/fallback.py` | Configurable retry policy |
| No pipeline health monitoring | Structured log export + alerting on validation failure rate |

Simulation retry note: forced-invalid records always fail retry in
simulation mode — this is intentional so the fallback path is always
demonstrable without live API calls.

---

## Supporting Files

| File | Purpose |
|---|---|
| [README.md](README.md) | Full system overview, architecture, routing table, stack, design decisions |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Live presenter script — step-by-step demo flow, expected questions, success criteria |
| [evals/EVAL_RESULTS.md](evals/EVAL_RESULTS.md) | Test set breakdown, validation failure modes, fallback behaviour, downstream protection gates |
| [ASSURANCE_ONE_PAGER.md](ASSURANCE_ONE_PAGER.md) | AI assurance summary — AI role, deterministic controls, human oversight, auditability, production gaps |
| [RUNBOOK.md](RUNBOOK.md) | Operational reference — start system, diagnose failures, inspect audit logs, recovery steps |
| [adr/001-validation-before-routing.md](adr/001-validation-before-routing.md) | Architecture Decision Record — why validation before routing, alternatives considered, production implications |
