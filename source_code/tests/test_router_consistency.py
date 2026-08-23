"""
Consistency tests between pages.py::_detect_intent_from_prompt and
engine.py::MultiAgentEngine._route_message.

These are two independently-maintained copies of the same "what kind of
message is this" logic — one decides what to fetch from the database, the
other decides how the AI should respond. They are supposed to agree, but
were found to have drifted apart during live testing: pages.py's continuity/
recall keyword list had phrases ("we were discussing", "what we discussed",
etc.) that engine.py's copy was missing, so a message correctly fetched as
memory-needing was still classified as ordinary chat when it came time to
respond — the exact mechanism behind a real "the bot didn't recall context"
complaint. That specific list was synced as part of the fix; this test
exists so future edits to either list get caught here instead of in a real
conversation again.
"""
import pytest
from pages import _detect_intent_from_prompt
from engine import MultiAgentEngine


@pytest.fixture
def engine():
    return MultiAgentEngine()


# (message, has_session_context) — has_session_context=True matches an
# ongoing conversation, which is when this drift actually manifests.
CASES = [
    "hi",
    "hello",
    "I've been really anxious about my exams and can't sleep well.",
    "can you suggest some breathing exercises to help me calm down",
    "do you have context what we were discussing?",
    "do you have context what we were discussing till now",
    "what did we talk about",
    "we discussed my career stress earlier right?",
    "what we have discussed so far?",
    "did i mention my relocation",
    "what did i tell you last time",
    "today i talked to my friend and her career is going great",
    "I am not feeling well today.",
    "what support can you give me?",
]


@pytest.mark.parametrize("message", CASES)
def test_routers_agree_on_intent(engine, message):
    pages_intent, _ = _detect_intent_from_prompt(message, has_session_context=True)

    references_past = engine._references_past(message)
    engine_route = engine._route_message(message, references_past=references_past, risk_hint="low")
    engine_intent = engine_route["intent_label"]

    assert pages_intent == engine_intent, (
        f"Router drift on {message!r}: pages.py says {pages_intent!r}, "
        f"engine.py says {engine_intent!r}"
    )


def test_the_original_drift_case_specifically(engine):
    """The exact real message that exposed the drift — kept as its own explicit
    test (not just a parametrize row) so a future failure here is unmistakable."""
    message = "do you have context what we were discussing?"
    pages_intent, _ = _detect_intent_from_prompt(message, has_session_context=True)
    references_past = engine._references_past(message)
    engine_intent = engine._route_message(message, references_past=references_past, risk_hint="low")["intent_label"]

    assert pages_intent == "continuity_followup"
    assert engine_intent == "continuity_followup"
