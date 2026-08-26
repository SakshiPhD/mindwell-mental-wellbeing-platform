"""
LangGraph-based router — single source of truth for "what kind of message is
this, and what does it need" (intent classification + memory-fetch decision).

This replaces the routing DECISION logic that used to be duplicated in two
places (engine.py::MultiAgentEngine._route_message and
pages.py::_detect_intent_from_prompt), which drifted apart from each other
three separate times during development (a missing keyword here, a missing
gate condition there) before anyone noticed. A LangGraph graph can't drift
from itself — there's only one definition.

Scope, deliberately narrow: this graph covers routing/classification only,
not the Safety/Memory/Coach LLM-calling sequence itself (that still lives in
engine.py::run_care_pipeline and hasn't caused a bug). Reuses the exact
keyword/regex constants already defined and tested in engine.py rather than
redefining them a third time, which would just create a new place to drift
from.

The graph is a direct translation of the existing "first matching rule
wins" if/elif chain into explicit nodes and conditional edges — same rules,
same order, now visible as a graph instead of buried in nested Python.
"""
import re
from typing import TypedDict, List

from langgraph.graph import StateGraph, END

from engine import (
    COPING_KEYWORDS,
    EMOTIONAL_SUPPORT_KEYWORDS,
    EVENT_MARKERS,
    EMOTION_WORDS,
    CONTINUITY_MARKERS,
    REPAIR_MARKERS,
    SAME_SESSION_RECALL_PATTERNS,
    SHORT_FOLLOWUP_MARKERS,
    PAST_REFERENCE_PHRASES,
    PAST_REFERENCE_REGEX,
)


class RouterState(TypedDict, total=False):
    # inputs
    user_text: str
    has_session_context: bool
    references_past: bool
    risk_hint: str
    continuity_trigger: bool
    is_greeting: bool
    # outputs
    intent_label: str
    response_mode: str
    memory_needed: str
    memory_types: List[str]
    escalation_flag: bool


_GREETING_KEYWORDS = {
    "hi", "hello", "hey", "hii", "hie", "yo", "sup",
    "good morning", "good evening", "good night",
}


def _keyword_hit(keywords, text: str) -> bool:
    """
    Match keywords against text, but with word boundaries for single-word
    keywords. Found by evaluations/routing_eval.py: plain substring
    matching (`kw in text`) made "help" match inside "helps", routing
    "thanks, that helps" into coping_request. Multi-word phrases keep using
    substring matching - a phrase like "what should i do" is already safe
    from this kind of accidental collision.
    """
    for kw in keywords:
        if " " in kw:
            if kw in text:
                return True
        elif re.search(rf"\b{re.escape(kw)}\b", text):
            return True
    return False


def _prepare(state: RouterState) -> RouterState:
    text = " ".join((state.get("user_text") or "").strip().lower().split())
    word_count = len(text.split())
    has_session_context = bool(state.get("has_session_context"))
    references_past = bool(state.get("references_past"))

    state["is_greeting"] = text in _GREETING_KEYWORDS

    short_followup_trigger = has_session_context and (
        text in SHORT_FOLLOWUP_MARKERS
        or any(text.startswith(m) for m in SHORT_FOLLOWUP_MARKERS)
        or (word_count <= 4 and any(m in text for m in SHORT_FOLLOWUP_MARKERS))
    )
    repair_trigger = has_session_context and any(m in text for m in REPAIR_MARKERS)
    # Not gated by has_session_context — matches engine.py's own comment on
    # this exact check: pages.py's equivalent never gated it either, and
    # gating it here was the specific bug the router-consistency tests caught.
    same_session_recall_trigger = any(p in text for p in SAME_SESSION_RECALL_PATTERNS)

    # Checked directly here rather than trusted purely from the caller-supplied
    # `references_past` flag: pages.py never computed that flag at all (only
    # engine.py's _references_past() did) — pages.py's old, pre-graph
    # continuity list simply had PAST_REFERENCE_PHRASES merged directly into
    # it. Cutting pages.py over to call this graph with references_past
    # hardcoded False initially lost that coverage (caught by the router
    # equivalence tests on "what did we talk about") until this check was
    # made self-contained instead of relying on every caller to supply it.
    past_reference_match = any(p in text for p in PAST_REFERENCE_PHRASES) or any(
        rx.search(text) for rx in PAST_REFERENCE_REGEX
    )

    state["continuity_trigger"] = (
        references_past
        or past_reference_match
        or any(m in text for m in CONTINUITY_MARKERS)
        or repair_trigger
        or same_session_recall_trigger
        or short_followup_trigger
    )
    return state


def _route_crisis(state: RouterState) -> str:
    if state.get("risk_hint") == "high":
        return "crisis"
    if state.get("is_greeting") and not state.get("continuity_trigger"):
        return "greeting"
    if state.get("continuity_trigger"):
        return "continuity"
    text = (state.get("user_text") or "").strip().lower()
    if _keyword_hit(COPING_KEYWORDS, text):
        return "coping"
    if any(kw in text for kw in EMOTIONAL_SUPPORT_KEYWORDS):
        return "emotional_support"
    has_event = any(marker in text for marker in EVENT_MARKERS)
    has_emotion = any(word in text for word in EMOTION_WORDS)
    if has_event and not has_emotion:
        return "event"
    if has_emotion:
        return "emotion"
    return "default"


def _set_crisis(state: RouterState) -> RouterState:
    state.update(
        intent_label="crisis",
        response_mode="crisis_support",
        memory_needed="full",
        memory_types=["current_session", "previous_sessions", "long_term_memory"],
        escalation_flag=True,
    )
    return state


def _set_greeting(state: RouterState) -> RouterState:
    state.update(
        intent_label="casual_greeting",
        response_mode="casual_chat",
        memory_needed="false",
        memory_types=[],
        escalation_flag=False,
    )
    return state


def _set_continuity(state: RouterState) -> RouterState:
    state.update(
        intent_label="continuity_followup",
        response_mode="supportive_chat",
        memory_needed="light",
        memory_types=["onboarding_profile", "current_session", "previous_sessions"],
        escalation_flag=False,
    )
    return state


def _set_coping(state: RouterState) -> RouterState:
    state.update(
        intent_label="coping_request",
        response_mode="coping_suggestion",
        memory_needed="light",
        memory_types=["onboarding_profile", "current_session", "long_term_memory"],
        escalation_flag=False,
    )
    return state


def _set_emotional_support(state: RouterState) -> RouterState:
    state.update(
        intent_label="emotional_support",
        response_mode="supportive_chat",
        memory_needed="light",
        memory_types=["onboarding_profile", "current_session", "long_term_memory"],
        escalation_flag=False,
    )
    return state


def _set_event(state: RouterState) -> RouterState:
    state.update(
        intent_label="event_sharing",
        response_mode="casual_chat",
        memory_needed="false",
        memory_types=[],
        escalation_flag=False,
    )
    return state


def _set_emotion(state: RouterState) -> RouterState:
    state.update(
        intent_label="emotional_response",
        response_mode="supportive_chat",
        memory_needed="light",
        memory_types=["current_session", "long_term_memory"],
        escalation_flag=False,
    )
    return state


def _set_default(state: RouterState) -> RouterState:
    state.update(
        intent_label="general_chat",
        response_mode="normal_chat",
        memory_needed="false",
        memory_types=[],
        escalation_flag=False,
    )
    return state


def build_router_graph():
    graph = StateGraph(RouterState)
    graph.add_node("prepare", _prepare)
    graph.add_node("crisis", _set_crisis)
    graph.add_node("greeting", _set_greeting)
    graph.add_node("continuity", _set_continuity)
    graph.add_node("coping", _set_coping)
    graph.add_node("emotional_support", _set_emotional_support)
    graph.add_node("event", _set_event)
    graph.add_node("emotion", _set_emotion)
    graph.add_node("default", _set_default)

    graph.set_entry_point("prepare")
    graph.add_conditional_edges(
        "prepare",
        _route_crisis,
        {
            "crisis": "crisis",
            "greeting": "greeting",
            "continuity": "continuity",
            "coping": "coping",
            "emotional_support": "emotional_support",
            "event": "event",
            "emotion": "emotion",
            "default": "default",
        },
    )
    for node in ("crisis", "greeting", "continuity", "coping", "emotional_support", "event", "emotion", "default"):
        graph.add_edge(node, END)

    return graph.compile()


_compiled_graph = None


def route(user_text: str, has_session_context: bool = False, references_past: bool = False,
          risk_hint: str = "low") -> dict:
    """Run the router graph and return the same shape MultiAgentEngine._route_message does."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_router_graph()

    result = _compiled_graph.invoke({
        "user_text": user_text,
        "has_session_context": has_session_context,
        "references_past": references_past,
        "risk_hint": risk_hint,
    })
    return {
        "intent_label": result["intent_label"],
        "response_mode": result["response_mode"],
        "memory_needed": result["memory_needed"],
        "memory_types": result["memory_types"],
        "escalation_flag": result["escalation_flag"],
    }
