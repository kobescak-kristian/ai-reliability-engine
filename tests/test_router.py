"""pipeline/router.py: validated output to a final business decision."""

import pytest

from config.settings import config
from models.schemas import AIOutput, FallbackAction, FinalDecision
from pipeline.router import route

THRESHOLD = config.CONFIDENCE_THRESHOLD


def _output(category, confidence):
    return AIOutput(category=category, confidence=confidence, reason="test")


@pytest.mark.parametrize("category", ["high_value", "low_value", "unknown"])
@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_fallback_flagged_always_goes_to_manual_review(category, confidence):
    # AGENTS.md constraint 3: a fallback-flagged record is never auto-routed.
    decision = route(_output(category, confidence), FallbackAction.MANUAL_REVIEW_FLAGGED, "r1")
    assert decision == FinalDecision.MANUAL_REVIEW


def test_high_value_at_threshold_goes_to_sales():
    decision = route(_output("high_value", THRESHOLD), FallbackAction.NONE, "r1")
    assert decision == FinalDecision.SEND_TO_SALES


def test_high_value_above_threshold_goes_to_sales():
    decision = route(_output("high_value", 1.0), FallbackAction.NONE, "r1")
    assert decision == FinalDecision.SEND_TO_SALES


def test_high_value_below_threshold_goes_to_manual_review():
    decision = route(_output("high_value", THRESHOLD - 0.01), FallbackAction.NONE, "r1")
    assert decision == FinalDecision.MANUAL_REVIEW


def test_low_value_goes_to_archive():
    decision = route(_output("low_value", 0.95), FallbackAction.NONE, "r1")
    assert decision == FinalDecision.ARCHIVE


def test_unknown_goes_to_manual_review():
    decision = route(_output("unknown", 0.95), FallbackAction.NONE, "r1")
    assert decision == FinalDecision.MANUAL_REVIEW


def test_successful_retry_routes_like_a_first_pass():
    decision = route(_output("low_value", 0.8), FallbackAction.RETRY, "r1")
    assert decision == FinalDecision.ARCHIVE
