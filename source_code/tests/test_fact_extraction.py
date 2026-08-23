"""
Regression tests for the two fact-extraction paths that feed user_memory:

1. pages.py::extract_storable_facts — decides which AI-extracted facts from
   a single turn are worth keeping. Two real bugs lived here: engine
   bookkeeping ("topic_state") was miscounted as a real fact when detecting
   the AI's legacy {"key":.., "value":..} output shape, and a filter
   discarded any fact whose value was literally "true"/"false" regardless
   of how meaningful the key name was (e.g. real production data:
   {"project_stress": "true"} was being silently dropped).

2. database.py::_extract_facts_from_messages — the deterministic, non-AI
   extractor that reliably powers chat_analysis and (as of the fix in this
   pass) also backstops user_memory when the AI's own per-turn extraction
   comes back empty.
"""
from pages import extract_storable_facts
from database import _extract_facts_from_messages


# ---------------------------------------------------------------------------
# extract_storable_facts (pages.py)
# ---------------------------------------------------------------------------

def test_real_bug_boolean_value_fact_is_kept():
    """Exact real production case that was being silently dropped before the fix."""
    result = extract_storable_facts({"project_stress": "true"})
    assert result == {"project_stress": "true"}


def test_topic_state_bookkeeping_is_never_stored():
    result = extract_storable_facts({
        "occupation": "nurse",
        "topic_state": {"current_topic": "career", "locked": True},
    })
    assert "topic_state" not in result
    assert result["occupation"] == "nurse"


def test_topic_state_contamination_does_not_break_legacy_shape_handling():
    """The exact real bug: a genuine {"key":.., "value":..} fact plus topic_state
    used to be miscounted as 3 keys, missed the legacy-shape check, and fell
    into a path that discarded it entirely."""
    result = extract_storable_facts({
        "key": "occupation",
        "value": "nurse",
        "topic_state": {"current_topic": "career", "locked": True},
    })
    assert result == {"occupation": "nurse"}


def test_literal_key_value_field_names_are_never_stored():
    """If the AI genuinely has no real key name and outputs plain key/value dicts
    that aren't the legacy 2-item shape, don't store garbage named "key"/"value"."""
    result = extract_storable_facts({"key": "a", "value": "b", "extra": "extra_value"})
    assert "key" not in result
    assert "value" not in result
    assert result.get("extra") == "extra_value"


def test_empty_new_fact_yields_nothing():
    assert extract_storable_facts({}) == {}


def test_non_dict_input_yields_nothing():
    assert extract_storable_facts(None) == {}
    assert extract_storable_facts("not a dict") == {}


def test_multiple_real_facts_all_kept():
    result = extract_storable_facts({
        "occupation": "nurse",
        "student_status": "nursing student",
        "topic_state": {"current_topic": "exam stress", "locked": True},
    })
    assert result == {"occupation": "nurse", "student_status": "nursing student"}


def test_trivially_short_values_are_dropped():
    result = extract_storable_facts({"x": "ok", "y": "a"})
    # "ok" is 2 chars (not > 2, dropped); "a" is 1 char (dropped)
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_facts_from_messages (database.py) — the deterministic backstop
# ---------------------------------------------------------------------------

def test_real_session_extracts_expected_stressors_and_coping():
    """Matches the real Aug 23 session this was verified against directly."""
    messages = [
        "I am not feeling well today.",
        "I have been feeling stressed because of work and I am not sleeping properly. What can I do tonight?",
        "tell me few calming activites other than bath, music.",
        "Writing sounds better, but whenever I start writing about work, I think about even more pending tasks.",
    ]
    facts = _extract_facts_from_messages(messages)
    assert facts.get("stressor_work") == "mentioned"
    assert facts.get("stressor_sleep") == "mentioned"
    assert facts.get("coping_creative") == "mentioned"  # "writing"


def test_no_signal_messages_extract_no_stressors():
    facts = _extract_facts_from_messages(["hi", "thanks", "bye"])
    assert not any(k.startswith("stressor_") for k in facts)


def test_empty_messages_list_extracts_nothing():
    assert _extract_facts_from_messages([]) == {}
