# Eval Results — AI Reliability Engine v2.0

## What Was Evaluated

The full 8-stage pipeline running in simulation mode against the
bundled test set (data/sample_input.json). Evaluation covers:
input sanitisation, AI output validation, fallback behaviour,
routing correctness, and downstream protection.

Simulation mode uses pre-seeded responses in pipeline/ai_processor.py
(SIMULATED dict + FORCED_FAILURES overrides). No live API calls.
Results are reproducible without an OpenAI key.

**Observed values below are from a live run on 2026-07-04**
(`python main.py`, fresh clone, run ID `run_20260704_031434_8cda36`,
default Windows console, no encoding env var, exit code 0).

---

## Test Set

| Property | Value |
|---|---|
| Total entries in sample_input.json | 51 (50 unique lead IDs; lead_046 appears twice as a repeat-lead test) |
| Passed validation (observed) | 44 (`validation_passed = 1` in SQLite) |
| Failed validation (observed) | 7 — 3 forced invalid outputs (lead_037–039) + 4 records with no usable AI response (lead_040, 041, 050 sanitiser-rejected; lead_042 has no simulation entry) |
| Sanitiser-rejected (pre-AI) | lead_040 (empty string), lead_041 (whitespace-only), lead_050 ("Hi" — 2 chars, below 5-char minimum). Rejected records still receive a decision: fallback safe default → manual_review |
| Sanitiser-stripped then processed | lead_042 (script tag + content removed → "Interested in your product"; no simulation entry, so it takes the fallback path in simulation — a live API run would classify it), lead_048 (HTML bold + script tag and content removed → classified high_value in simulation) |
| Long input | lead_047 — 1262 chars, below the 2000-char truncation limit, **not truncated**; the truncation path is not exercised by this test set. Classified high_value 0.99 |
| Repeat lead | lead_046 (submitted twice — both processed and persisted; Google Sheets flags the repeat on second submission when Sheets is enabled — CLI with credentials only) |
| Non-English input | lead_049 (German — classified correctly in simulation) |

---

## Validation Failures

### Forced failure modes (leads 037–039)

`_force_invalid` is a top-level key in sample_input.json that
`pipeline/input_handler.py` moves into `metadata` before
constructing `InputRecord`. This makes it readable by `ai_processor._simulate()`.

Each forced record returns a seeded invalid response on both the initial call
and the strict-prompt retry (FORCED_FAILURES does not define a separate
strict-mode path — `_simulate()` returns the same forced response regardless
of the `strict` flag).

| Lead | Injected fault | Validator error observed |
|---|---|---|
| lead_037 | `bad_category` — returns `"maybe_value"` | `Invalid category 'maybe_value' — must be one of {'high_value', 'low_value', 'unknown'}` |
| lead_038 | `confidence_out_of_range` — returns `-0.3` | `Confidence out of range: -0.3 — must be 0.0–1.0` |
| lead_039 | `empty_reason` — returns `reason: ""` | `Missing or empty field: reason` |

(FORCED_FAILURES also seeds `1.85` and `2.0` variants for other leads,
but only the variants selected by `_force_invalid` in sample_input.json
are exercised — the value observed at runtime is `-0.3`.)

### Allowed categories (source: pipeline/validator.py line 4)

```python
ALLOWED_CATEGORIES = {"high_value", "low_value", "unknown"}
```

Any other string causes an immediate validation failure.

### Expected vs observed

| Scenario | Expected | Observed (run 2026-07-04) |
|---|---|---|
| Valid AI output | Validation passes; routes per routing table | 44 records passed; routed 22 send_to_sales / 10 archive / 12 manual_review (unknown or below threshold) |
| Invalid category | Validator catches → fallback retry → safe default | lead_037: caught, retry failed, safe default, `manual_review` |
| Out-of-range confidence | Validator catches → fallback retry → safe default | lead_038 (`-0.3`): caught, retry failed, safe default, `manual_review` |
| Empty reason | Validator catches → fallback retry → safe default | lead_039: caught, retry failed, safe default, `manual_review` |
| AI returns None | Validator returns `valid=False, errors=["AI returned no output"]` → fallback | lead_040, 041, 042, 050: all four caught, safe default, `manual_review` |

Every failed record is persisted with `validation_passed = 0` and the
original validation error string in the `notes` column, e.g.:

```
lead_038 | validation_passed=0 | manual_review_flagged | manual_review
       | notes: Fallback triggered. Errors: Confidence out of range: -0.3 — must be 0.0–1.0
```

---

## Fallback Behaviour

Fallback logic is in `pipeline/fallback.py`. MAX_RETRIES = 1.

**Stage 1 — retry with strict prompt:**
On validation failure, `handle_fallback()` calls
`ai_processor.process_record(record, strict=True)`.
The strict prompt enforces exact JSON structure with no extra text.

**Stage 2 — safe default:**
If the retry also fails validation, the system assigns:
```
category="unknown", confidence=0.0,
reason="System default — AI output failed validation after retry."
```
This output is guaranteed to pass validation and routes to `manual_review`.
The safe default's own re-validation is a consistency check only — the
persisted and alerted validation result is the ORIGINAL AI output's.

**Forced-failure behaviour in simulation mode:**
All three forced records (lead_037, lead_038, lead_039) return an invalid
response on both the initial call and the retry. Retry always fails →
safe default always assigned → `MANUAL_REVIEW_FLAGGED` for all three.
This is intentional for demo reproducibility.

**History note:** earlier revisions of the README stated "Fallback
triggered on 2 records," later "3 records" — both derived from code
analysis, not a run. The observed count is **7**: the 3 forced failures
plus the 4 no-output records (sanitiser-rejected and missing simulation
entry) also flow through fallback. The README now states 7.

| Metric | Value (observed, run 2026-07-04) |
|---|---|
| Forced failures in test set | 3 records (lead_037, lead_038, lead_039) |
| Fallbacks triggered | 7 (3 forced + lead_040, 041, 042, 050) |
| Retry succeeded | 0 (expected — forced/no-output records cannot recover in simulation) |
| Safe default assigned | 7 |

---

## Manual Review Routing

Routing logic is in `pipeline/router.py`. Manual review is triggered by:

| Condition | Source |
|---|---|
| `fallback_action == MANUAL_REVIEW_FLAGGED` | Fallback stage 2 — always overrides category |
| `category == "high_value"` + `confidence < 0.60` | Confidence below threshold (env var, default 0.60) |
| `category == "unknown"` | AI uncertain or insufficient info |

**Records observed routing to manual_review (19 total, run 2026-07-04):**

- lead_026–030: `category=unknown`, confidence 0.25–0.45 (5)
- lead_031–035: `high_value` but confidence 0.48–0.57, below 0.60 threshold (5)
- lead_036: gibberish, `unknown`, confidence 0.05 (1)
- lead_037–039: forced failures → safe default → `MANUAL_REVIEW_FLAGGED` (3)
- lead_040, 041, 042, 050: no usable AI output → safe default → `MANUAL_REVIEW_FLAGGED` (4)
- lead_045: `high_value`, confidence 0.58 → `manual_review` (1)
- lead_043: `high_value`, confidence exactly 0.60 → routed to `send_to_sales`
  (threshold check is `conf >= threshold`, so 0.60 passes — observed)

**Full decision distribution (observed):** send_to_sales 22 ·
manual_review 19 · archive 10. Alerts queued: 19.

---

## Downstream Protection

| Gate | What it prevents |
|---|---|
| Sanitiser — null/non-string check | Non-string input never reaches the AI call |
| Sanitiser — empty after cleaning | lead_040 (empty string) rejected before AI |
| Sanitiser — < 5 chars | lead_050 ("Hi") rejected before AI |
| Sanitiser — whitespace-only | lead_041 rejected before AI |
| Sanitiser — script/style removal | lead_042, lead_048 — script tags AND their body content removed before the AI call (content regex runs before tag stripping) |
| Sanitiser — truncation at 2000 chars | Truncation path exists but is not exercised by this test set (longest input, lead_047, is 1262 chars) |
| Validator — category enum | Invalid category strings never reach the router |
| Validator — confidence range | Out-of-range floats (`-0.3` observed) never reach the router |
| Validator — reason non-empty | Empty reason field never routes |
| Fallback safe default | Always valid — cannot itself fail validation |
| Router — `MANUAL_REVIEW_FLAGGED` checked first | Fallback-flagged records always go to manual_review regardless of category or confidence |
| Sheets writes use `RAW` | Lead-supplied text is never evaluated as a spreadsheet formula |

---

## Known Limitations of This Eval

- All results are from simulation mode (pre-seeded responses in
  `pipeline/ai_processor.py`). Live API behaviour will differ —
  real model outputs are not deterministic. In simulation, any input
  whose lead ID is not pre-seeded takes the fallback path.
- MAX_RETRIES = 1. A single retry may not be sufficient for transient
  model errors. Production would require exponential backoff.
- Forced failures always exhaust retry in simulation. A real model may
  self-correct on retry more often than the test set implies.
- No load or concurrency testing. SQLite is single-writer; concurrent
  API calls under load are not evaluated here.
- The 2000-char truncation path is untested by the bundled sample data.
