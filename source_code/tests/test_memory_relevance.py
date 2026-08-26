"""
Regression tests for MultiAgentEngine._build_relevant_memory_recall - the
function that scores which past sessions are relevant to the current
message. First dedicated test coverage for this function; found by
evaluations/memory_relevance_eval.py.

Real bug covered here: plain substring matching (`key in haystack`) let
"work" match inside "...time working." in an unrelated session's summary,
pulling it in as a false distractor purely from the collision - not because
the sessions were actually related. Fixed with word-boundary matching.
"""
import pytest
from engine import MultiAgentEngine


@pytest.fixture
def engine():
    return MultiAgentEngine()


SESSION_HISTORY = [
    {"session_id": "s0", "date": "2026-08-20", "tone": "stressed",
     "summary": "User talked about feeling overwhelmed with work deadlines and a demanding boss.",
     "facts": {}},
    {"session_id": "s1", "date": "2026-08-15", "tone": "frustrated",
     "summary": "User shared a conflict with their partner about spending too much time working.",
     "facts": {}},
    {"session_id": "s2", "date": "2026-08-10", "tone": "tired",
     "summary": "User mentioned trouble sleeping and feeling exhausted most nights.",
     "facts": {}},
]


def test_work_query_does_not_leak_unrelated_partner_session(engine):
    """'work' must not match inside 'working' and pull in the unrelated
    partner-conflict session."""
    result = engine._build_relevant_memory_recall(
        "I am so stressed about my deadlines at work again",
        {"session_history": SESSION_HISTORY},
        min_score=3,
    )
    assert "work deadlines" in result
    assert "conflict with their partner" not in result


def test_sleep_query_does_not_leak_unrelated_work_session(engine):
    """'feel' must not match inside 'feeling' and pull in the unrelated
    work-stress session."""
    result = engine._build_relevant_memory_recall(
        "I cant sleep at night and feel so exhausted",
        {"session_history": SESSION_HISTORY},
        min_score=3,
    )
    assert "trouble sleeping" in result
    assert "work deadlines" not in result


def test_genuinely_relevant_session_still_recalled(engine):
    """The word-boundary fix must not have weakened real matches."""
    result = engine._build_relevant_memory_recall(
        "things with my partner have been tense lately",
        {"session_history": SESSION_HISTORY},
        min_score=3,
    )
    assert "conflict with their partner" in result


def test_no_relevant_session_returns_empty(engine):
    result = engine._build_relevant_memory_recall(
        "what is the weather like today",
        {"session_history": SESSION_HISTORY},
        min_score=3,
        allow_recent_fallback=False,
    )
    assert result == ""
