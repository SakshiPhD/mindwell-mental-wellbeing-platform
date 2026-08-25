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


def test_everyday_help_refusal_stays_low_risk():
    """Found by evaluations/safety_crisis_eval.py: bare 'don't need help'
    matched mundane refusals. Narrowed to require 'anymore'."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "No thanks, I don't need help with this assignment, I've got it covered."
    )
    assert risk == "low"
    assert is_extreme is False


def test_everyday_already_tried_stays_low_risk():
    """Found by evaluations/safety_crisis_eval.py: bare 'already tried'
    matched ordinary past-tense sentences."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "I already tried the new restaurant downtown, it was great"
    )
    assert risk == "low"
    assert is_extreme is False


def test_everyday_no_more_stays_low_risk():
    """Found by evaluations/safety_crisis_eval.py: bare 'no more' matched
    completely unrelated sentences."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "There's no more milk in the fridge, can you grab some?"
    )
    assert risk == "low"
    assert is_extreme is False


def test_everyday_completely_done_stays_low_risk():
    """Found by evaluations/safety_crisis_eval.py: bare 'completely done'
    matched ordinary task-completion sentences."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "I'm completely done with this project, finally submitted it!"
    )
    assert risk == "low"
    assert is_extreme is False


def test_narrowed_keywords_still_catch_genuine_crisis():
    """The narrowing must not have weakened real detection for the
    surrounding case that motivated it."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "it's decided, no more talking, i already tried once and i know what works this time"
    )
    assert is_extreme is True
    assert risk == "high"


def test_negated_ability_paraphrase_is_caught():
    """Found by evaluations/safety_crisis_eval.py: 'can't go on' is a listed
    keyword, but 'I don't think I can go on' expresses the same hopelessness
    through negation-of-positive phrasing, which plain substring matching
    can't see. This was a real missed-recall case (crisis_recall was 13/14
    before this fix)."""
    is_extreme, risk, flagged = _detect_extreme_crisis(
        "I don't think I can go on much longer"
    )
    assert risk == "medium"
    assert is_extreme is False
    assert flagged == ["don't think i can go on (paraphrase)"]


def test_negated_ability_regex_variants_all_caught():
    for msg in [
        "I don't think I can continue like this anymore",
        "I'm not sure I can cope",
        "I don't know if I can keep going",
    ]:
        is_extreme, risk, flagged = _detect_extreme_crisis(msg)
        assert risk == "medium", f"expected medium risk for: {msg!r}, got {risk}"


def test_negated_ability_phrasing_with_benign_object_stays_low_risk():
    """The fix above must not fire on ordinary uses of 'go on'/'continue'
    followed by a noun object (going on vacation/a trip, continuing a
    subscription) - verified directly since these are exactly the shape of
    false positive this eval exists to catch."""
    benign = [
        "I dont think I can go on vacation this year",
        "I am not sure I can go on the trip with you",
        "not sure I can continue this subscription",
        "I dont think I can go on with this diet",
    ]
    for msg in benign:
        is_extreme, risk, flagged = _detect_extreme_crisis(msg)
        assert risk == "low", f"false positive on: {msg!r} (flagged={flagged})"
