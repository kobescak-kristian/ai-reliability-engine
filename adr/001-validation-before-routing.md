# ADR-001 — Validate AI Output Before Routing

**Status:** Accepted
**Date:** 2026-06-19
**Author:** Kristian Kobescak

---

## Context

The pipeline classifies inbound leads using an LLM (OpenAI gpt-4o-mini).
The model returns a JSON object with three fields: `category`, `confidence`,
and `reason`. The category field drives the routing decision — which determines
whether a lead reaches a sales team, is archived, or is flagged for human review.

LLM output is probabilistic. Observed failure modes (seeded in
`pipeline/ai_processor.py` FORCED_FAILURES and documented in
`evals/EVAL_RESULTS.md`) include:

- Invalid category value (`"maybe_value"`, `"medium_value"`, `""`)
- Confidence out of 0.0–1.0 range (`1.85`, `-0.3`, `2.0`)
- Empty required field (`reason: ""`)
- Non-JSON response or API call failure (returns `None`)

Downstream systems — sales CRM, Google Sheets Action Queue, notification
layer — do not validate the data they receive. If an invalid category
reaches the router, behaviour is undefined. If the router silently maps an
unknown value to an arbitrary decision, the failure is invisible and
untraceable.

---

## Decision

**Validate every AI output against a strict schema before any routing
decision is made. No field from the AI response is trusted until it
passes validation.**

Validation rules (`pipeline/validator.py`):
1. `category` must be in `{"high_value", "low_value", "unknown"}`
2. `confidence` must be a float in `[0.0, 1.0]`
3. `reason` must be a non-empty string after stripping whitespace

On validation failure, the fallback layer fires (`pipeline/fallback.py`)
before any routing occurs. The router (`pipeline/router.py`) never receives
an unvalidated AI output.

The fallback sequence:
1. Retry with a stricter prompt (MAX_RETRIES = 1)
2. If retry also fails: assign a deterministic safe default
   (`category="unknown", confidence=0.0, reason="System default — AI output
   failed validation after retry."`) and flag as `MANUAL_REVIEW_FLAGGED`

The safe default is constructed in code — not from the model — and is
guaranteed to pass validation.

---

## Alternatives Considered

**Trust the model and route directly**
Simpler pipeline with no validation layer. Fails silently when the model
returns unexpected output. A wrong category in the router produces an
unhandled path or a wrong downstream action with no log trail. Rejected —
silent failure is unacceptable in an operational workflow.

**Validate only category; trust confidence**
Partial validation. Still allows out-of-range confidence values to reach
the router. The router compares confidence against a threshold — an
out-of-range value (e.g. `1.85`) would incorrectly pass the threshold
check and auto-action a lead that should be reviewed. Rejected.

**Rules-based classification only (no AI)**
Removes the validation problem by removing the AI. Also removes the ability
to handle ambiguous, mixed-signal, and unstructured input — the cases that
rules-based classification cannot resolve. Out of scope for this system.

**Broad try/except with silent default**
Use exception handling to absorb validation failures without surfacing
them. Produces silent errors — the same failure mode as trusting the model
directly, with added indirection. Rejected.

---

## Consequences

**Positive:**
- Every routing decision is grounded in validated, schema-conforming data
- Invalid AI output is immediately visible: logged, fallback fires, alert queued
- Downstream systems receive only valid data — no defensive validation needed there
- Every decision — including fallback reason and validation errors — is persisted
  in SQLite with a run ID for cross-run traceability

**Trade-offs:**
- Validation adds one pipeline stage (negligible latency — in-process Pydantic check)
- Fallback retry adds one additional model call on validation failure
- Three pipeline modules (`validator.py`, `fallback.py`, `router.py`) must be
  kept consistent if the AI output schema changes

**What would change in production:**
- Replace field-level Pydantic validation with a versioned JSON Schema registry
  if AI output format evolves independently of this codebase
- Add per-field validation failure telemetry to detect model drift before it
  becomes a production incident (e.g. rising empty-reason rate signals prompt
  degradation)
- `CONFIDENCE_THRESHOLD` is a single global env var. Production deployments
  serving multiple use cases may need per-use-case threshold configuration
- MAX_RETRIES = 1 is sufficient for demo and single-tenant use. Production:
  exponential backoff with a dead-letter queue for records that exhaust retries
- The safe default (`category="unknown", confidence=0.0`) always routes to
  `manual_review`. In a high-volume production system, volume of safe defaults
  should be monitored — a spike indicates prompt or model regression
