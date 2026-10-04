"""pipeline/fallback.py: one bounded retry, then a deterministic safe default.

Every test replaces ai_processor.process_record, so no model path runs.
"""

import pytest

from models.schemas import AIOutput, FallbackAction, InputRecord, ValidationResult
from pipeline import ai_processor, fallback

FAILED = ValidationResult(valid=False, errors=["AI returned no output"])


@pytest.fixture
def record():
    return InputRecord(id="r1", raw_text="test lead")


@pytest.fixture
def calls(monkeypatch):
    """Replace the model call; tests set calls['returns'] and read calls['log']."""
    state = {"returns": None, "log": []}

    def fake_process_record(rec, strict=False):
        state["log"].append({"id": rec.id, "strict": strict})
        return state["returns"]

    monkeypatch.setattr(ai_processor, "process_record", fake_process_record)
    return state


def test_retry_success_returns_retry(record, calls):
    good = AIOutput(category="low_value", confidence=0.8, reason="Retried cleanly.")
    calls["returns"] = good
    output, action = fallback.handle_fallback(record, FAILED)
    assert action == FallbackAction.RETRY
    assert output == good


def test_retry_uses_strict_prompt_once(record, calls):
    calls["returns"] = AIOutput(category="low_value", confidence=0.8, reason="ok")
    fallback.handle_fallback(record, FAILED)
    assert calls["log"] == [{"id": "r1", "strict": True}]


def test_invalid_retry_gives_flagged_safe_default(record, calls):
    calls["returns"] = AIOutput.model_construct(category="bogus", confidence=0.8, reason="x")
    output, action = fallback.handle_fallback(record, FAILED)
    assert action == FallbackAction.MANUAL_REVIEW_FLAGGED
    assert output == fallback.DEFAULT_SAFE_OUTPUT


def test_none_retry_gives_flagged_safe_default(record, calls):
    calls["returns"] = None
    output, action = fallback.handle_fallback(record, FAILED)
    assert action == FallbackAction.MANUAL_REVIEW_FLAGGED
    assert output == fallback.DEFAULT_SAFE_OUTPUT


def test_retry_budget_exhausted_makes_no_call(record, calls):
    output, action = fallback.handle_fallback(record, FAILED, attempt=fallback.MAX_RETRIES)
    assert calls["log"] == []
    assert action == FallbackAction.MANUAL_REVIEW_FLAGGED
    assert output == fallback.DEFAULT_SAFE_OUTPUT


def test_safe_default_is_unknown_with_zero_confidence():
    assert fallback.DEFAULT_SAFE_OUTPUT.category == "unknown"
    assert fallback.DEFAULT_SAFE_OUTPUT.confidence == 0.0
    assert fallback.DEFAULT_SAFE_OUTPUT.reason.strip()
