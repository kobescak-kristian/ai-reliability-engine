"""pipeline/validator.py: schema checks on AI output before routing (ADR-001)."""

from models.schemas import AIOutput
from pipeline.validator import ALLOWED_CATEGORIES, validate


def _output(category="high_value", confidence=0.9, reason="Clear buying intent."):
    # model_construct skips pydantic coercion, so malformed values reach
    # the validator exactly as a bad model response would deliver them.
    return AIOutput.model_construct(category=category, confidence=confidence, reason=reason)


def test_valid_output_passes():
    result = validate(_output(), "r1")
    assert result.valid is True
    assert result.errors == []


def test_every_allowed_category_passes():
    for category in ALLOWED_CATEGORIES:
        assert validate(_output(category=category), "r1").valid is True


def test_none_output_fails():
    result = validate(None, "r1")
    assert result.valid is False
    assert result.errors == ["AI returned no output"]


def test_invalid_category_fails():
    result = validate(_output(category="medium_value"), "r1")
    assert result.valid is False
    assert any("Invalid category 'medium_value'" in e for e in result.errors)


def test_missing_category_fails():
    result = validate(_output(category=""), "r1")
    assert result.valid is False
    assert "Missing field: category" in result.errors


def test_confidence_out_of_range_fails():
    for confidence in (-0.01, 1.01):
        result = validate(_output(confidence=confidence), "r1")
        assert result.valid is False
        assert any("Confidence out of range" in e for e in result.errors)


def test_confidence_bounds_are_inclusive():
    for confidence in (0.0, 1.0):
        assert validate(_output(confidence=confidence), "r1").valid is True


def test_non_numeric_confidence_fails():
    for confidence in ("high", None):
        result = validate(_output(confidence=confidence), "r1")
        assert result.valid is False
        assert any("Confidence not numeric" in e for e in result.errors)


def test_empty_reason_fails():
    for reason in ("", "   "):
        result = validate(_output(reason=reason), "r1")
        assert result.valid is False
        assert "Missing or empty field: reason" in result.errors


def test_all_errors_are_reported_together():
    result = validate(_output(category="bogus", confidence=2.0, reason=""), "r1")
    assert result.valid is False
    assert len(result.errors) == 3
