# Eval Results — AI Reliability Engine v2.0

## What Was Evaluated

The full 8-stage pipeline running in simulation mode against the
bundled test set (data/sample_input.json). Evaluation covers:
input sanitisation, AI output validation, fallback behaviour,
routing correctness, and downstream protection.

Simulation mode uses pre-seeded responses in pipeline/ai_processor.py
(SIMULATED dict + FORCED_FAILURES overrides). No live API calls.
Results are reproducible without an OpenAI key.

---

## Test Set

| Property | Value |
|---|---|
| Total entries in sample_input.json | 51 (50 unique lead IDs; lead_046 appears twice as a repeat-lead test) |
| Confirmed passing validation | TODO — run pipeline and record count from `GET /stats` |
| Confirmed failing validation (forced) | 3 records (lead_037, lead_038, lead_039) |
| Sanitiser-rejected (pre-AI) | lead_040 (empty string), lead_041 (whitespace-only), lead_050 ("Hi" — 2 chars, below 5-char minimum) |
| Sanitiser-stripped then classified | lead_042 (XSS script tag stripped to plain text), lead_048 (HTML bold + script tag stripped) |
| Long input truncated | lead_047 (truncated from ~1700 chars to 2000-char limit; classified correctly after truncation) |
| Repeat lead | lead_046 (submitted twice — both processed; Google Sheets flags repeat on second submission) |
| Non-English input | lead_049 (German — classified correctly in simulation) |

---

## Validation Failures

### Forced failure modes (leads 037–039)

`_force_invalid` is a top-level key in sample_input.json that
`pipeline/input_handler.py` (lines 24–27) moves into `metadata` before
constructing `InputRecord`. This makes it readable by `ai_processor._simulate()`.

Each forced record returns a seeded invalid response on both the initial call
and the strict-prompt retry (FORCED_FAILURES does not define a separate
strict-mode path — `_simulate()` returns the same forced response regardless
of the `strict` flag).

| Lead | Injected fault | Validator error triggered |
|---|---|---|
| lead_037 | `bad_category` — returns `"maybe_value"` | `Invalid category 'maybe_value' — must be one of {'high_value', 'low_value', 'unknown'}` |
| lead_038 | `confidence_out_of_range` — returns `1.85` | `Confidence out of range: 1.85 — must be 0.0–1.0` |
| lead_039 | `empty_reason` — returns `reason: ""` | `Missing or empty field: reason` |

### Allowed categories (source: pipeline/validator.py line 4)

```python
ALLOWED_CATEGORIES = {"high_value", "low_value", "unknown"}
```

Any other string causes an immediate validation failure.

### Expected vs observed

| Scenario | Expected | Observed |
|---|---|---|
| Valid AI output | Validation passes; routes per routing table | TODO — confirm with run output |
| Invalid category | Validator catches → fallback retry → safe default | TODO |
| Out-of-range confidence | Validator catches → fallback retry → safe default | TODO |
| Empty reason | Validator catches → fallback retry → safe default | TODO |
| AI returns None | Validator returns `valid=False, errors=["AI returned no output"]` → fallback | TODO |

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

**Forced-failure behaviour in simulation mode:**
All three forced records (lead_037, lead_038, lead_039) return an invalid
response on both the initial call and the retry. Retry always fails →
safe default always assigned → `MANUAL_REVIEW_FLAGGED` for all three.
This is intentional for demo reproducibility.

**Note on README:** The README states "Fallback triggered on 2 records."
Code analysis shows 3 records trigger fallback (lead_037, 038, 039 — all
seeded as forced failures, all exhausting retry). The README figure is
incorrect. Actual count to be confirmed by running `python main.py` and
reading `GET /stats` → `fallbacks_triggered`.

| Metric | Value |
|---|---|
| Forced failures in test set | 3 records (lead_037, lead_038, lead_039) |
| Expected fallbacks triggered | 3 (all exhausting MAX_RETRIES = 1 → safe default) |
| Retry succeeded | TODO — confirm from run output (expected: 0 for forced records) |
| Safe default assigned | TODO — confirm from run output (expected: 3) |

---

## Manual Review Routing

Routing logic is in `pipeline/router.py`. Manual review is triggered by:

| Condition | Source |
|---|---|
| `fallback_action == MANUAL_REVIEW_FLAGGED` | Fallback stage 2 — always overrides category |
| `category == "high_value"` + `confidence < 0.60` | Confidence below threshold (env var, default 0.60) |
| `category == "unknown"` | AI uncertain or insufficient info |

**Records expected to route to manual_review in this test set:**

- lead_026–030: `category=unknown`, confidence 0.25–0.45
- lead_031–035: `high_value` but confidence 0.48–0.57 (below 0.60 threshold)
- lead_036: gibberish, `unknown`, confidence 0.05
- lead_037–039: forced failures → safe default → `MANUAL_REVIEW_FLAGGED`
- lead_043: `high_value`, confidence exactly 0.60 → routes to `send_to_sales`
  (threshold check is `conf >= threshold`, so 0.60 passes)
- lead_045: `high_value`, confidence 0.58 → routes to `manual_review`
- lead_050: sanitiser rejects ("Hi") → no routing decision

TODO: Run pipeline and record exact `manual_review` count from `GET /stats`.

---

## Downstream Protection

| Gate | What it prevents |
|---|---|
| Sanitiser — null/non-string check | Non-string input never reaches the AI call |
| Sanitiser — empty after cleaning | lead_040, lead_042 (post-strip empty) rejected before AI |
| Sanitiser — < 5 chars | lead_050 ("Hi") rejected before AI |
| Sanitiser — whitespace-only | lead_041 rejected before AI |
| Sanitiser — HTML strip | lead_042, lead_048 — script tags removed; plain text reaches AI |
| Sanitiser — truncation at 2000 chars | lead_047 truncated; token abuse prevented |
| Validator — category enum | Invalid category strings never reach the router |
| Validator — confidence range | Out-of-range floats (1.85, -0.3) never reach the router |
| Validator — reason non-empty | Empty reason field never routes |
| Fallback safe default | Always valid — cannot itself fail validation |
| Router — `MANUAL_REVIEW_FLAGGED` checked first | Fallback-flagged records always go to manual_review regardless of category or confidence |

---

## Known Limitations of This Eval

- All results are from simulation mode (pre-seeded responses in
  `pipeline/ai_processor.py`). Live API behaviour will differ —
  real model outputs are not deterministic.
- MAX_RETRIES = 1. A single retry may not be sufficient for transient
  model errors. Production would require exponential backoff.
- Forced failures always exhaust retry in simulation. A real model may
  self-correct on retry more often than the test set implies.
- No load or concurrency testing. SQLite is single-writer; concurrent
  API calls under load are not evaluated here.
- TODO: Run a live pipeline session and capture `GET /stats` output to
  replace all TODO markers above with observed counts.
