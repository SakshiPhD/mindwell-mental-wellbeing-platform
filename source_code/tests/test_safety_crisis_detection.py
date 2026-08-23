"""
Regression tests for pages.py::_detect_extreme_crisis.

Covers the exact false positive found and fixed during live testing: the
bare keyword "the end" matched ordinary text like "...questions at the end
of each sentence" and incorrectly triggered crisis-support mode. Also
protects the thing that fix must never break: genuine crisis phrasing must
still be caught.
"""
from pages import _detect_extreme_crisis


def test_real_false_positive_no_longer_triggers():
    """The exact real message that incorrectly triggered 'crisis' before the fix."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "why do you always ask repeated questions at the end of each sentence?"
    )
    assert risk == "low"
    assert is_extreme is False
    assert flagged == []


def test_everyday_end_phrases_stay_low_risk():
    everyday = [
        "at the end of the day I just want to relax",
        "till the end of the movie it was great",
        "can we talk at the end of the meeting?",
    ]
    for msg in everyday:
        is_extreme, risk, flagged = _detect_extreme_crisis(msg)
        assert risk == "low", f"false positive on: {msg!r} (flagged={flagged})"


def test_genuine_extreme_crisis_still_detected():
    """The fix must not have weakened real detection — verified directly, not assumed."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "this is the end, I cant do this anymore, its decided, no going back"
    )
    assert risk == "high"
    assert is_extreme is True
    assert "this is the end" in flagged
    assert "no going back" in flagged


def test_genuine_extreme_crisis_with_plan_and_means():
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "I have a plan and everything I need, this is the end"
    )
    assert is_extreme is True
    assert risk == "high"


def test_single_high_risk_keyword_is_medium_not_high():
    is_extreme, risk, flagged = _detect_extreme_crisis("nobody cares about me anymore")
    assert is_extreme is False
    assert risk == "medium"


def test_benign_message_is_low_risk():
    is_extreme, risk, flagged = _detect_extreme_crisis("I had a great day today, thanks for asking!")
    assert risk == "low"
    assert is_extreme is False
    assert flagged == []


def test_empty_message_is_low_risk():
    is_extreme, risk, flagged = _detect_extreme_crisis("")
    assert risk == "low"
    assert is_extreme is False
