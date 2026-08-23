"""
Regression tests for MultiAgentEngine._find_unverified_recall_topic — the
code-level guardrail against the AI confidently confirming a "do you
remember X" question when X was never actually in the real context.

Two real bugs lived in this exact function during development, both covered
here:
- the context checked always ends with the current question echoed back in
  (e.g. "User: you remember about my relocation?"), so without excluding it
  the topic word the person just used would always trivially match itself.
- plain substring matching missed simple word-form variants (the user asks
  about "relocation" but the stored context says "relocated").
"""
import pytest
from engine import MultiAgentEngine


@pytest.fixture
def engine():
    return MultiAgentEngine()


def test_topic_not_in_context_triggers_guardrail(engine):
    """The real failing case: nothing in context mentions relocation."""
    context = (
        "User: hey, today i am not feeling good.\n"
        "Assistant: Aw, sorry to hear that, friend.\n"
        "User: i talked to my friend and her career is going great\n"
        "Assistant: That's really great to hear!\n"
        "User: you remember about my relocation?"
    )
    topic = engine._find_unverified_recall_topic("you remember about my relocation?", context)
    assert topic == "relocation"


def test_topic_present_exactly_does_not_trigger(engine):
    context = (
        "User: i relocated to qatar last year and im still jobless\n"
        "Assistant: That sounds really tough.\n"
        "User: do you remember about my relocation?"
    )
    topic = engine._find_unverified_recall_topic("do you remember about my relocation?", context)
    assert topic is None


def test_topic_present_as_word_form_variant_does_not_trigger(engine):
    """'relocation' (noun) vs 'relocated' (verb) in the stored context — must still match."""
    context = "User: i relocated to qatar last year\nUser: do you remember about my relocation?"
    topic = engine._find_unverified_recall_topic("do you remember about my relocation?", context)
    assert topic is None


def test_current_question_is_not_used_as_its_own_evidence(engine):
    """Context containing ONLY the current question (no real prior turns) must still trigger."""
    context = "User: did i ever tell you about my health?"
    topic = engine._find_unverified_recall_topic("did i ever tell you about my health?", context)
    assert topic == "health"


def test_generic_recall_question_without_named_topic_does_not_trigger(engine):
    """'what do you remember?' names no specific topic — nothing to check, let the LLM answer."""
    context = "User: i am stressed about my project deadline"
    topic = engine._find_unverified_recall_topic("what do you remember?", context)
    assert topic is None


def test_non_recall_message_does_not_trigger(engine):
    topic = engine._find_unverified_recall_topic("I've been really anxious about my exams.", "")
    assert topic is None


def test_empty_message_does_not_trigger(engine):
    topic = engine._find_unverified_recall_topic("", "some context")
    assert topic is None


def test_real_health_example_from_production(engine):
    """did i ever tell you about my health? — the exact real message that fabricated before the fix."""
    context = "User: i am stressed about my project deadline\nAssistant: That sounds stressful."
    topic = engine._find_unverified_recall_topic("did i ever tell you about my health?", context)
    assert topic == "health"
