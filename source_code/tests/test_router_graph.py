"""
Equivalence tests for router_graph.py against the two implementations it's
meant to replace (engine.py::MultiAgentEngine._route_message and
pages.py::_detect_intent_from_prompt). These are the gate that had to pass
before pages.py/engine.py were ever pointed at the graph for real: every
case here — including every real bug case found this session — must
produce identical routing decisions through all paths.
"""
import pytest
from router_graph import route
from pages import _detect_intent_from_prompt
from engine import MultiAgentEngine


@pytest.fixture
def engine():
    return MultiAgentEngine()


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
    "why do you always ask repeated questions at the end of each sentence?",
    "this is the end, I cant do this anymore, its decided, no going back",
    "I dont want to live anymore",
]


@pytest.mark.parametrize("message", CASES)
def test_graph_matches_both_existing_routers(engine, message):
    pages_intent, _ = _detect_intent_from_prompt(message, has_session_context=True)
    references_past = engine._references_past(message)
    has_session_context = bool(engine._session_buffer)
    engine_route = engine._route_message(message, references_past=references_past, risk_hint="low")
    graph_route = route(message, has_session_context=has_session_context, references_past=references_past, risk_hint="low")

    assert graph_route["intent_label"] == pages_intent, (
        f"{message!r}: graph={graph_route['intent_label']!r} vs pages={pages_intent!r}"
    )
    assert graph_route["intent_label"] == engine_route["intent_label"], (
        f"{message!r}: graph={graph_route['intent_label']!r} vs engine={engine_route['intent_label']!r}"
    )


def test_graph_matches_engine_on_full_routing_payload(engine):
    """Not just intent_label — the whole decision, for a representative case."""
    message = "can you suggest some breathing exercises to help me calm down"
    engine_route = engine._route_message(message, references_past=False, risk_hint="low")
    graph_route = route(message, has_session_context=False, references_past=False, risk_hint="low")
    assert graph_route == engine_route


def test_graph_matches_engine_on_crisis_risk_hint(engine):
    """The one path that must never be wrong: risk_hint='high' -> full crisis routing."""
    message = "I dont want to live anymore"
    engine_route = engine._route_message(message, references_past=False, risk_hint="high")
    graph_route = route(message, has_session_context=False, references_past=False, risk_hint="high")

    assert graph_route == engine_route
    assert graph_route["intent_label"] == "crisis"
    assert graph_route["escalation_flag"] is True
    assert graph_route["memory_needed"] == "full"


def test_graph_greeting_short_circuits_regardless_of_continuity_when_no_session():
    graph_route = route("hi", has_session_context=False, references_past=False, risk_hint="low")
    assert graph_route["intent_label"] == "casual_greeting"
    assert graph_route["memory_needed"] == "false"


def test_thanks_that_helps_is_not_coping_request():
    """Found by evaluations/routing_eval.py: plain substring matching made
    the coping keyword 'help' match inside 'helps', misrouting a plain
    thank-you into coping-suggestion mode."""
    graph_route = route("thanks, that helps", has_session_context=False, references_past=False, risk_hint="low")
    assert graph_route["intent_label"] == "general_chat"


def test_genuine_help_request_still_routes_to_coping():
    """The word-boundary fix must not have weakened real detection - 'help'
    as its own word must still trigger coping_request."""
    for message in [
        "I need help, I am so stressed",
        "can you suggest some breathing exercises to help me calm down",
        "what techniques can help me manage panic attacks",
    ]:
        graph_route = route(message, has_session_context=False, references_past=False, risk_hint="low")
        assert graph_route["intent_label"] == "coping_request", (
            f"{message!r} -> {graph_route['intent_label']!r}"
        )
