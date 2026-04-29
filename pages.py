"""
Page Functions for MindWell application.
Contains all page rendering functions for the application.
"""
import streamlit as st
import uuid
import re
import time
import random
import html as html_mod
import threading
import traceback
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

import psycopg2
import requests

from styles import load_css
from database import (
    register_user, verify_user_login, verify_user_email_password,
    update_verification, save_onboarding,
    save_chat_message, load_specific_session,
    fetch_all_user_context, fetch_selective_context, get_pooled_connection, get_session_last_activity,
    finalize_session_analysis,
)
from config import DEMO_MODE

import queue as _queue
_pending_save_queue = _queue.Queue()
SESSION_IDLE_MINUTES = 15
_session_finalize_timers = {}
_session_finalize_lock = threading.Lock()


# Keyword definitions (exact match from engine.py)
_EMOTIONAL_SUPPORT_KEYWORDS = {
    "stress", "stressed", "anxious", "anxiety", "worried", "worry", "overthinking",
    "sad", "low", "hopeless", "tired", "exhausted", "burnout", "overwhelmed",
    "lonely", "angry", "frustrated", "panic", "empty"
}

_COPING_KEYWORDS = {
    "help", "suggest", "advice", "cope", "coping", "manage", "what should i do",
    "how can i", "exercise", "breathe", "breathing", "routine", "habit", "focus"
}


def check_response_grounded(response_text, rag_meta):
    """
    Check if response actually uses/references the retrieved RAG chunks.

    Returns: (is_grounded: bool, grounding_score: float)
    Score 0.0-1.0 indicates confidence that response is grounded in chunks.
    """
    if not rag_meta or not response_text:
        return False, 0.0

    response_lower = response_text.lower()
    response_words = set(response_text.lower().split())
    grounding_signals = []

    # 1. CHECK FOR EXACT PHRASES FROM CHUNKS
    for chunk_meta in rag_meta:
        chunk_text = chunk_meta.get("chunk_text", "").lower()
        if not chunk_text:
            continue

        # Extract key phrases (3-5 word sequences)
        chunk_words = chunk_text.split()
        for i in range(len(chunk_words) - 2):
            phrase = " ".join(chunk_words[i:i+3])
            if phrase in response_lower:
                grounding_signals.append(("exact_phrase", 0.8))
                break

    # 2. CHECK FOR CITATION LANGUAGE
    citation_patterns = [
        r"according to",
        r"based on",
        r"the document",
        r"the guide",
        r"research shows",
        r"studies show",
        r"from the",
        r"the following",
        r"steps are",
        r"technique",
        r"method",
    ]
    for pattern in citation_patterns:
        if re.search(pattern, response_lower):
            grounding_signals.append(("citation_language", 0.6))
            break

    # 3. CHECK KEYWORD OVERLAP WITH CHUNKS
    max_overlap = 0.0
    for chunk_meta in rag_meta:
        chunk_text = chunk_meta.get("chunk_text", "")
        if not chunk_text:
            continue
        chunk_words = set(chunk_text.lower().split())
        # Calculate Jaccard similarity
        if len(chunk_words) > 0:
            overlap = len(response_words & chunk_words) / len(chunk_words | response_words)
            max_overlap = max(max_overlap, overlap)

    if max_overlap > 0.3:  # 30%+ word overlap = significant reference
        grounding_signals.append(("keyword_overlap", 0.7 if max_overlap > 0.5 else 0.5))

    # 4. CHECK RESPONSE LENGTH (longer responses more likely to use chunks)
    if len(response_text) > 150:  # Detailed response
        grounding_signals.append(("response_detail", 0.4))

    # Calculate final grounding score
    if not grounding_signals:
        return False, 0.0

    grounding_score = sum(score for _, score in grounding_signals) / len(grounding_signals)
    is_grounded = grounding_score >= 0.5  # 50%+ confidence threshold

    logger.debug(f"Grounding analysis: signals={grounding_signals}, score={grounding_score:.2f}, grounded={is_grounded}")
    return is_grounded, grounding_score

# New keyword sets for smarter intent classification
_EVENT_MARKERS = {
    "went to", "visited", "happened", "today i", "yesterday i", "we had",
    "i met", "i saw", "i attended", "just came from", "i finished", "i completed",
    "i started", "i joined", "i got", "i found", "i bought", "i tried",
    "i did", "we went", "we did", "there was", "he said", "she said",
    "they told", "i heard", "i read", "i watched", "got invited", "was invited"
}

_EMOTION_WORDS = {
    "sad", "happy", "anxious", "scared", "depressed", "overwhelmed",
    "stressed", "angry", "frustrated", "lonely", "hurt", "worried",
    "upset", "devastated", "hopeless", "numb", "guilty", "ashamed",
    "relieved", "excited", "nervous", "afraid", "broken", "lost",
    "crying", "cried", "can't sleep", "cant sleep", "exhausted",
    "miserable", "terrible", "awful", "horrible"
}

_GREETING_KEYWORDS = {
    "hi", "hello", "hey", "hii", "hie", "yo", "sup", "hiii",
    "good morning", "good evening", "good night"
}

# CRITICAL: Extreme Crisis Keywords (immediate high risk)
# These indicate IMMINENT DANGER - specific plan + means + timeline + finality
_EXTREME_CRISIS_KEYWORDS = {
    # Specific plan indicators
    "i have a plan", "specific plan", "i'm ready to act", "ready to act",
    "everything i need", "have everything i need",

    # Means/Method indicators (CRITICAL)
    "i'm holding", "holding the pills", "have the pills", "holding the knife",
    "have the rope", "have the gun", "gun in hand", "pills in hand",
    "the overdose", "lethal dose", "cut myself", "overdose",

    # Extreme Timeline (IMMEDIATE DANGER)
    "in 5 minutes", "in 10 minutes", "in 30 minutes", "in an hour",
    "tonight i", "this is happening tonight", "happening tonight",
    "right now", "at this very moment", "immediately",
    "it's over", "it's happening", "i'm doing this",

    # Finality/No Return
    "this is my last", "last conversation", "won't respond after",
    "i'm done", "completely done", "no more", "it's decided",
    "no going back", "the end", "it's final", "final decision",
    "no more talking", "don't try to stop me", "won't be stopped",

    # Previous Attempts (HIGH RISK)
    "already tried", "tried once", "previous attempt",
    "i know what works", "i know how to", "second time", "try again",

    # Absolute Hopelessness
    "nothing helps", "nothing works", "tried everything",
    "beyond help", "no way out", "beyond saving",

    # Refusal of Help (combined with above)
    "don't need help", "don't need steps", "don't want to talk",
    "stop trying to help", "your words don't help"
}

# HIGH RISK Keywords (requires escalation, not immediate danger yet)
_HIGH_RISK_KEYWORDS = {
    # Suicidal ideation + contemplation
    "want to die", "i'm dying", "want to end it", "end the pain",
    "kill myself", "hurt myself", "harm myself", "take my life",
    "can't do this", "can't continue", "can't go on",

    # Strong intent indicators
    "i will", "i'm going to", "i plan to", "i decided to",
    "no point", "no reason to live", "not worth living",

    # Hopelessness + isolation
    "nobody cares", "no one understands", "alone", "isolated",
    "no hope", "hopeless", "worthless", "burden",
}

_CONTINUITY_MARKERS = [
    # Past conversation references (from engine.py PAST_REFERENCE_PHRASES)
    "do you remember", "remember what", "we discussed", "we talked about",
    "last time", "earlier", "before", "previously", "past session", "yesterday",
    "still the same", "same situation", "same problem", "same issue",
    "nothing changed", "hasn't changed", "hasnt changed", "not changed",
    "still dealing", "still struggling", "still going through", "still facing",
    "as i said", "like i said", "like i mentioned", "you know about",
    "you know my", "already told you", "what we were talking", "continue from",
    "continuing", "same as before", "same thing", "remember my",
    "what did we talk about", "what were we talking about", "do you recall",
    "same as yesterday", "same as last week", "as we discussed", "as discussed",

    # Current session references (original markers)
    "last reply", "previous reply", "your reply", "your last reply",
    "last sentence", "previous message", "earlier message",
    "what you said", "you said", "you just said", "finish your sentence",
    "check your last", "check your reply", "see your last",
    "incomplete", "cut off", "truncated", "you were saying", "finish what you said",
    "previous messages", "our previous messages",
    "you could not fetch", "you forgot", "you missed", "complete your sentence",
    "what i told you last", "what did i tell you last", "did i tell you anything",
    "did i mention", "what did i say", "what do you understand",
    "few messages ago", "this conversation", "in this same conversation",
    "our current conversation", "what i told you", "what reason i gave",
    "your last sentence is incomplete", "complete the sentence", "what after",
    "you replied me", "you replied", "what did you mean after",
    "what comes after", "you are not taking the context",
    "do you know what we were discussing", "you replied me",
    "complete that sentence", "finish your sentence",
    "finish that line", "finish your last line",
]

_SAME_SESSION_RECALL_PATTERNS = [
    "what did i tell you", "what did i say", "did i mention",
    "do you remember what we were discussing", "what were we discussing",
    "this conversation", "in this conversation", "in this same conversation",
    "what was it", "what was that", "so what was", "tell me what",
    "you said", "what did you say", "what exactly", "what i told",
    "i told you", "i said", "i have told you", "i already told",
    # Additional patterns for user variations
    "what we have discussed", "what we discussed", "we discussed",
    "what we talked about", "we talked about", "remember discussing",
    "we were discussing", "about what we", "earlier we",
]

_SHORT_FOLLOWUP_MARKERS = {
    "continue", "go on", "tell me more", "yes continue", "yes, continue",
    "yes explore", "explore", "complete it", "complete your sentence",
    "yes acknowledge", "acknowledge", "elaborate",
    "okay continue", "ok continue", "carry on",
}


def _detect_extreme_crisis(prompt: str) -> tuple:
    """
    Detect EXTREME CRISIS (imminent danger) from specific keywords.

    Returns: (is_extreme_crisis: bool, risk_level: str, flagged_keywords: list)

    Extreme Crisis = plan + means + timeline + finality
    High Risk = suicidal ideation but not extreme
    """
    if not prompt:
        return False, "low", []

    text = prompt.strip().lower()
    flagged = []

    # Check for extreme crisis keywords
    extreme_count = sum(1 for kw in _EXTREME_CRISIS_KEYWORDS if kw in text)
    high_risk_count = sum(1 for kw in _HIGH_RISK_KEYWORDS if kw in text)

    # Extreme Crisis: 2+ extreme keywords (plan + means + timeline + finality)
    if extreme_count >= 2:
        for kw in _EXTREME_CRISIS_KEYWORDS:
            if kw in text:
                flagged.append(kw)
        return True, "high", flagged[:5]  # Top 5 keywords

    # High Risk: 1+ extreme OR 2+ high risk keywords
    if extreme_count >= 1 or high_risk_count >= 2:
        for kw in _EXTREME_CRISIS_KEYWORDS:
            if kw in text:
                flagged.append(kw)
        for kw in _HIGH_RISK_KEYWORDS:
            if kw in text:
                flagged.append(kw)
        return False, "high", flagged[:5]

    # Medium Risk: 1+ high risk keyword
    if high_risk_count >= 1:
        for kw in _HIGH_RISK_KEYWORDS:
            if kw in text:
                flagged.append(kw)
        return False, "medium", flagged[:3]

    return False, "low", []


def _get_rag_needed_for_intent(intent: str) -> bool:
    """
    Determine if RAG documents are needed for this intent.

    RAG mapping (ONLY when knowledge base is beneficial):
    - casual_greeting → False (no context needed)
    - event_sharing → False (pure event = LLM handles it)
    - emotional_response → False (emotional validation, not techniques)
    - emotional_support → False (needs emotional validation, not techniques)
    - continuity_followup → False (focused on past conversations, not knowledge base)
    - general_chat → False (casual chat doesn't need RAG)
    - crisis → True (crisis needs risk resources)
    - coping_request → True (needs techniques, methods, advice from knowledge base)
    """
    rag_needed = {
        "casual_greeting": False,
        "event_sharing": False,
        "emotional_response": False,
        "crisis": True,        # NEEDS RAG: risk resources
        "continuity_followup": False,
        "coping_request": True,  # NEEDS RAG: techniques, methods, advice
        "emotional_support": False,
        "general_chat": False,
    }
    return rag_needed.get(intent, False)


def _get_rag_top_k(intent: str, user_message: str) -> int:
    """
    Fetch all available chunks - filtering by similarity handles the rest.

    Returns a high number (all available) because the REAL filtering happens
    via similarity_score threshold, not chunk count.

    Strategy: Get all candidates, keep only those that match query meaning (similarity >= threshold).
    If 1 chunk is 0.80 similar → use 1
    If 20 chunks are 0.65+ similar → use 20
    Accuracy depends on relevance, not on maximum chunks.
    """
    # Fetch all available chunks - similarity threshold will do the real work
    return 100  # Fetch up to 100, keep only those >= similarity threshold


def _filter_chunks_by_relevance(rag_chunks, similarity_threshold=0.65):
    """
    Filter retrieved chunks to keep only highly relevant ones.

    Returns only chunks with similarity_score >= threshold.
    This way: 2 chunks with 0.8+ score are better than 8 chunks with 0.4 score.

    Args:
        rag_chunks: List of chunk metadata dicts with 'similarity_score'
        similarity_threshold: Minimum relevance score (0.0-1.0)

    Returns:
        Filtered list of relevant chunks, sorted by score (descending)
    """
    if not rag_chunks:
        return []

    # Filter by threshold
    relevant = [
        chunk for chunk in rag_chunks
        if chunk.get("similarity_score", 0) >= similarity_threshold
    ]

    # Sort by score (highest first)
    relevant.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

    logger.debug(
        f"Chunk filtering: {len(rag_chunks)} retrieved → "
        f"{len(relevant)} relevant (threshold >= {similarity_threshold})"
    )

    return relevant


def _detect_intent_from_prompt(prompt: str, has_session_context: bool = False) -> tuple:
    """
    Intent detection matching exact engine.py logic.
    Returns: (intent_label, memory_types)

    OPTIMIZED: Only fetch memory that's NECESSARY:
    - Onboarding profile removed (not needed for any case)
    - Fetch only: current_session, long_term_memory, previous_sessions
    - Smart event vs emotional distinction
    """
    if not prompt:
        return "general_chat", []

    text = prompt.strip().lower()
    word_count = len(text.split())

    # Check greeting (exact match or from set)
    is_greeting = text in _GREETING_KEYWORDS

    # Check continuity markers
    continuity_trigger = (
        any(marker in text for marker in _CONTINUITY_MARKERS)
        or any(pattern in text for pattern in _SAME_SESSION_RECALL_PATTERNS)
    )

    # Short followup (requires session context)
    short_followup_trigger = has_session_context and (
        text in _SHORT_FOLLOWUP_MARKERS
        or any(text.startswith(m) for m in _SHORT_FOLLOWUP_MARKERS)
        or (word_count <= 4 and any(m in text for m in _SHORT_FOLLOWUP_MARKERS))
    )

    if continuity_trigger or short_followup_trigger:
        continuity_trigger = True

    # Route based on exact engine.py logic
    if is_greeting and not continuity_trigger:
        intent = "casual_greeting"
        memory_types = []  # No memory needed
        return intent, memory_types

    if continuity_trigger:
        intent = "continuity_followup"
        memory_types = ["current_session", "previous_sessions"]
        return intent, memory_types

    if any(kw in text for kw in _COPING_KEYWORDS):
        intent = "coping_request"
        memory_types = ["current_session", "long_term_memory"]
        return intent, memory_types

    if any(kw in text for kw in _EMOTIONAL_SUPPORT_KEYWORDS):
        intent = "emotional_support"
        memory_types = ["current_session", "long_term_memory"]
        return intent, memory_types

    # NEW: Smart event vs emotional response distinction
    has_event = any(marker in text for marker in _EVENT_MARKERS)
    has_emotion = any(word in text for word in _EMOTION_WORDS)

    if has_event and not has_emotion:
        intent = "event_sharing"
        memory_types = []  # Pure event = LLM handles it
        return intent, memory_types

    if has_emotion:
        intent = "emotional_response"
        memory_types = ["current_session", "long_term_memory"]  # Track emotional patterns
        return intent, memory_types

    # Default: general chat (LLM is capable alone)
    intent = "general_chat"
    memory_types = []
    return intent, memory_types


def _should_use_rag(query: str) -> bool:
    """
    Determine if RAG retrieval is beneficial for this query.
    Smart detection: Only use RAG for information-seeking queries,
    NOT for emotional sharing, greetings, or casual chat.

    Returns: True only if query seeks knowledge/advice/techniques
    """
    if not query or not isinstance(query, str):
        return False

    query_clean = query.strip().lower()

    # Skip very short messages
    if len(query_clean) < 15:
        return False

    # Skip common greetings and simple acknowledgments
    trivial_responses = {
        'hi', 'hello', 'hey', 'hii', 'hey there',
        'ok', 'okay', 'k', 'yes', 'yeah', 'no', 'nope',
        'thanks', 'thank you', 'ty', 'sure', 'cool', 'nice', 'good',
        'bye', 'goodbye', 'see you', 'take care', 'lol', 'haha'
    }

    if query_clean in trivial_responses:
        return False

    # Skip if message is mostly punctuation/emojis
    alphanumeric_count = sum(1 for c in query_clean if c.isalnum())
    if alphanumeric_count < len(query_clean) * 0.5:
        return False

    # EMOTIONAL SHARING PATTERNS (NO RAG NEEDED - needs empathy, not info)
    emotional_sharing_patterns = [
        "i feel", "i'm feeling", "im feeling", "i am feeling",
        "i'm sad", "im sad", "i am sad",
        "i'm happy", "im happy", "i am happy",
        "i'm stressed", "im stressed", "i am stressed",
        "i'm anxious", "im anxious", "i am anxious",
        "i'm tired", "im tired", "i am tired",
        "i'm upset", "im upset", "i am upset",
        "i'm depressed", "im depressed", "i am depressed",
        "i hate", "i love", "i miss",
        "today was", "yesterday was", "this week",
        "my day", "my life", "my mood",
    ]
    is_emotional_sharing = any(pattern in query_clean for pattern in emotional_sharing_patterns)

    # KNOWLEDGE-SEEKING PATTERNS (RAG IS USEFUL)
    knowledge_seeking_patterns = [
        # Explicit questions
        "how to", "how do", "how can", "how should",
        "what is", "what are", "what's the", "what should",
        "why do", "why does", "why is",
        "when should", "when is", "when do",
        "where can", "where do",
        # Advice/technique seeking
        "technique", "method", "strategy", "way to", "ways to",
        "tips for", "tips on", "advice for", "advice on",
        "help me with", "help with",
        "suggest", "recommend",
        "cope with", "coping with", "deal with", "manage",
        "overcome", "get over", "get through",
        # Learning
        "explain", "teach me", "tell me about",
        "learn", "understand",
        "exercise for", "practice for",
    ]
    is_knowledge_seeking = any(pattern in query_clean for pattern in knowledge_seeking_patterns)

    # Decision:
    # - If knowledge-seeking → use RAG (even if emotional tone present)
    # - If purely emotional sharing → skip RAG
    # - Else → skip RAG (conservative default)
    if is_knowledge_seeking:
        return True
    if is_emotional_sharing:
        return False

    # Default: skip RAG unless clearly information-seeking
    return False


def _schedule_session_finalization(user_id, session_id, idle_minutes=SESSION_IDLE_MINUTES):
    """Finalize one session once inactivity threshold is reached."""
    if not user_id or not session_id:
        return

    user_key = str(user_id)
    session_key = str(session_id)
    key = (user_key, session_key)
    idle_seconds = max(int(idle_minutes * 60), 1)
    last_activity = get_session_last_activity(user_id, session_key)
    if last_activity:
        elapsed = (datetime.now() - last_activity).total_seconds()
        delay_seconds = 1 if elapsed >= idle_seconds else int(idle_seconds - elapsed) + 1
    else:
        delay_seconds = idle_seconds

    def _run():
        try:
            with _session_finalize_lock:
                active_timer = _session_finalize_timers.get(key)
                if active_timer is not timer:
                    return

            latest_activity = get_session_last_activity(user_id, session_key)
            if not latest_activity:
                return

            elapsed = (datetime.now() - latest_activity).total_seconds()
            if elapsed < idle_seconds:
                _schedule_session_finalization(user_id, session_key, idle_minutes=idle_minutes)
                return

            finalized = finalize_session_analysis(user_id, session_key)
            if finalized:
                logger.info(
                    "Auto-finalized session after %d-minute inactivity: user=%s session=%s",
                    idle_minutes, user_key, session_key
                )
                _load_sidebar_chats.clear()
        except Exception as e:
            logger.warning("Auto-session finalization failed for session %s: %s", session_key, e)
        finally:
            with _session_finalize_lock:
                if _session_finalize_timers.get(key) is timer:
                    _session_finalize_timers.pop(key, None)

    timer = threading.Timer(delay_seconds, _run)
    timer.daemon = True
    with _session_finalize_lock:
        old_timer = _session_finalize_timers.get(key)
        if old_timer:
            try:
                old_timer.cancel()
            except Exception:
                pass
        _session_finalize_timers[key] = timer
    timer.start()


def safe_html(text):
    """Escape user content to prevent XSS."""
    return html_mod.escape(str(text))


_ERROR_FALLBACKS = [
    "I'm still with you, {name}. Let me try that again.",
    "Something went wrong on my end, {name}, but I'm still listening. Could you say that once more?",
    "I stumbled a bit, {name}. I'm here - go ahead and try again.",
    "I had a brief hiccup, {name}. I'm ready now - what were you saying?",
    "I missed that due to a glitch, {name}. I'm back and listening.",
]


def _fallback_message(user_name):
    name = (user_name or "there").strip().split()[0]
    return random.choice(_ERROR_FALLBACKS).format(name=name)


@st.cache_data(ttl=30, show_spinner=False)
def _load_sidebar_chats(user_id):
    """Cached sidebar chat list."""
    def _clean_summary_for_display(summary_text):
        """Remove internal metadata from summary before displaying to user."""
        if not summary_text:
            return ""
        # Remove internal markers
        text = summary_text.replace("Referenced history:", "").strip()
        text = text.replace("Topic:", "").strip()
        text = text.replace("Tone:", "").strip()
        text = text.replace("Key user details:", "").strip()
        text = text.replace(" | ", " ").strip()
        return text[:100]  # Cap at 100 chars for sidebar

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                WITH session_rollup AS (
                    SELECT
                        cm.session_id,
                        MAX(cm.user_msg_timestamp) AS last_activity
                    FROM chat_messages cm
                    WHERE cm.user_id = %s
                    GROUP BY cm.session_id
                )
                SELECT
                    s.session_id,
                    COALESCE(ca.summary_text, fm.user_message) AS title,
                    s.last_activity
                FROM session_rollup s
                LEFT JOIN LATERAL (
                    SELECT cm.user_message
                    FROM chat_messages cm
                    WHERE cm.user_id = %s
                      AND cm.session_id = s.session_id
                    ORDER BY cm.user_msg_timestamp ASC
                    LIMIT 1
                ) fm ON TRUE
                LEFT JOIN LATERAL (
                    SELECT summary_text
                    FROM chat_analysis ca
                    WHERE ca.user_id = %s
                      AND ca.session_id = s.session_id
                    ORDER BY COALESCE(ca.last_updated, ca.created_at) DESC
                    LIMIT 1
                ) ca ON TRUE
                ORDER BY s.last_activity DESC
                LIMIT 20
                """,
                (user_id, user_id, user_id),
            )
            rows = cur.fetchall()
            # Clean summaries before displaying in sidebar
            cleaned_rows = []
            for sess_id, title, activity in rows:
                cleaned_title = _clean_summary_for_display(title) if title else "Chat"
                cleaned_rows.append((sess_id, cleaned_title, activity))
            return cleaned_rows
        finally:
            cur.close()


def _get_recent_session_id(user_id, max_idle_minutes=SESSION_IDLE_MINUTES):
    """Resume recent active session after refresh."""
    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT session_id, MAX(COALESCE(bot_msg_timestamp, user_msg_timestamp)) AS last_activity
                FROM chat_messages
                WHERE user_id = %s
                GROUP BY session_id
                ORDER BY last_activity DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            sess_id, last_activity = row
            if not last_activity:
                return None
            if datetime.now() - last_activity <= timedelta(minutes=max_idle_minutes):
                return str(sess_id)
            try:
                finalized = finalize_session_analysis(user_id, str(sess_id))
                if finalized:
                    logger.info("Session finalized after inactivity: user=%s session=%s", user_id, sess_id)
                    _load_sidebar_chats.clear()
            except Exception as e:
                logger.warning("Inactive session finalization skipped: %s", e)
            return None
        finally:
            cur.close()


def _roll_session_if_idle(user_id, idle_minutes=SESSION_IDLE_MINUTES):
    """If current session is idle beyond threshold, finalize it and start a new one."""
    session_id = st.session_state.get("session_id")
    if not session_id:
        return False

    try:
        last_activity = get_session_last_activity(user_id, session_id)
    except Exception as e:
        logger.warning("Failed to read session activity: %s", e)
        return False

    if not last_activity:
        return False

    if datetime.now() - last_activity < timedelta(minutes=idle_minutes):
        return False

    try:
        finalized = finalize_session_analysis(user_id, str(session_id))
        if finalized:
            _load_sidebar_chats.clear()
    except Exception as e:
        logger.warning("Failed to finalize idle session %s: %s", session_id, e)

    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.chat_title = "New Conversation"
    st.query_params["session_id"] = st.session_state.session_id
    logger.info("Started new session after %d-minute inactivity window", idle_minutes)
    return True


def _finalize_due_sessions(user_id, idle_minutes=SESSION_IDLE_MINUTES, limit=5, target_session_id=None):
    """Finalize any stale sessions that crossed inactivity cutoff and still lack summary."""
    cutoff = datetime.now() - timedelta(minutes=idle_minutes)
    rows = []
    for attempt in (1, 2):
        with get_pooled_connection() as conn:
            if not conn:
                return 0
            cur = conn.cursor()
            try:
                query = """
                    WITH sess AS (
                        SELECT
                            cm.session_id,
                            MAX(COALESCE(cm.bot_msg_timestamp, cm.user_msg_timestamp)) AS last_activity
                        FROM chat_messages cm
                        WHERE cm.user_id = %s
                        GROUP BY cm.session_id
                    )
                    SELECT
                        s.session_id,
                        COALESCE(
                            (
                                SELECT ca.summary_text
                                FROM chat_analysis ca
                                WHERE ca.user_id = %s AND ca.session_id = s.session_id
                                ORDER BY COALESCE(ca.last_updated, ca.created_at) DESC
                                LIMIT 1
                            ),
                            ''
                        ) AS summary_text
                    FROM sess s
                    WHERE s.last_activity <= %s
                """
                params = [user_id, user_id, cutoff]
                if target_session_id:
                    query += " AND s.session_id = %s"
                    params.append(str(target_session_id))
                query += " ORDER BY s.last_activity DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt == 1:
                    logger.warning("Stale-session scan failed (stale connection, retrying once): %s", e)
                    continue
                logger.warning("Stale-session scan failed: %s", e)
                return 0
            except Exception as e:
                logger.warning("Stale-session scan failed: %s", e)
                return 0
            finally:
                cur.close()

    finalized_count = 0
    for sess_id, summary_text in rows:
        if str(summary_text or "").strip():
            continue
        try:
            if finalize_session_analysis(user_id, str(sess_id)):
                finalized_count += 1
        except Exception as e:
            logger.warning("Failed to finalize stale session %s: %s", sess_id, e)
    if finalized_count:
        _load_sidebar_chats.clear()
    return finalized_count


# ===================== GEOLOCATION DATA =====================
try:
    from countries_states_cities.countries import Countries
    HAS_CSC = True
except ImportError:
    HAS_CSC = False


@st.cache_resource
def load_geolocation_data():
    """Load all countries with their states and cities"""
    if HAS_CSC:
        try:
            countries_obj = Countries()
            all_countries = countries_obj.all()
            country_dict = {}
            
            for country in all_countries[:100]:
                country_name = country.get('name', '')
                country_id = country.get('id', '')
                
                states_obj = Countries.states_of(country_id)
                states = states_obj.all() if states_obj else []
                
                states_dict = {}
                for state in states[:50]:
                    state_name = state.get('name', '')
                    state_id = state.get('id', '')
                    
                    cities_obj = Countries.cities_of(state_id)
                    cities = cities_obj.all() if cities_obj else []
                    
                    city_names = [city.get('name', '') for city in cities[:30]]
                    if city_names:
                        states_dict[state_name] = city_names
                
                if states_dict:
                    country_dict[country_name] = states_dict
            
            return country_dict if country_dict else get_fallback_data()
        except Exception as e:
            return get_fallback_data()
    else:
        return get_fallback_data()


def get_fallback_data():
    """Fallback data if library fails - comprehensive world data"""
    return {
        "India": {
            "Maharashtra": ["Mumbai", "Pune", "Nagpur", "Aurangabad", "Nashik", "Kolhapur"],
            "Delhi": ["New Delhi", "Central Delhi", "East Delhi", "West Delhi", "South Delhi"],
            "Karnataka": ["Bangalore", "Mysore", "Mangalore", "Belgaum", "Udupi"],
            "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Salem", "Tiruchirappalli"],
            "Telangana": ["Hyderabad", "Warangal", "Nizamabad", "Karimnagar"],
            "West Bengal": ["Kolkata", "Darjeeling", "Asansol", "Siliguri"],
            "Uttar Pradesh": ["Lucknow", "Kanpur", "Varanasi", "Agra", "Meerut"],
            "Gujarat": ["Ahmedabad", "Surat", "Vadodara", "Rajkot"],
            "Rajasthan": ["Jaipur", "Jodhpur", "Udaipur", "Ajmer"],
        },
        "United States": {
            "California": ["Los Angeles", "San Francisco", "San Diego", "Sacramento", "Fresno"],
            "Texas": ["Houston", "Dallas", "Austin", "San Antonio", "Fort Worth"],
            "New York": ["New York City", "Buffalo", "Rochester", "Yonkers"],
            "Florida": ["Miami", "Orlando", "Tampa", "Jacksonville", "Fort Lauderdale"],
            "Illinois": ["Chicago", "Springfield", "Peoria"],
            "Pennsylvania": ["Philadelphia", "Pittsburgh"],
            "Ohio": ["Columbus", "Cleveland", "Cincinnati"],
        },
        "United Kingdom": {
            "England": ["London", "Manchester", "Birmingham", "Leeds", "Liverpool"],
            "Scotland": ["Edinburgh", "Glasgow", "Aberdeen", "Dundee"],
            "Wales": ["Cardiff", "Swansea", "Newport"],
            "Northern Ireland": ["Belfast", "Derry"],
        },
        "Canada": {
            "Ontario": ["Toronto", "Ottawa", "Hamilton", "London"],
            "British Columbia": ["Vancouver", "Victoria", "Surrey"],
            "Quebec": ["Montreal", "Quebec City", "Laval"],
            "Alberta": ["Calgary", "Edmonton"],
        },
        "Australia": {
            "New South Wales": ["Sydney", "Newcastle", "Wollongong", "Central Coast"],
            "Victoria": ["Melbourne", "Geelong", "Ballarat"],
            "Queensland": ["Brisbane", "Gold Coast", "Cairns"],
            "Western Australia": ["Perth", "Fremantle"],
        },
        "Germany": {
            "Bavaria": ["Munich", "Nuremberg", "Augsburg", "Regensburg"],
            "North Rhine-Westphalia": ["Cologne", "Dsseldorf", "Dortmund"],
            "Berlin": ["Berlin"],
            "Hamburg": ["Hamburg"],
        },
        "France": {
            "le-de-France": ["Paris", "Versailles", "Boulogne"],
            "Provence-Alpes-Cte d'Azur": ["Marseille", "Nice", "Cannes"],
            "Auvergne-Rhne-Alpes": ["Lyon", "Grenoble"],
            "Occitanie": ["Toulouse", "Montpellier"],
        },
        "Japan": {
            "Tokyo": ["Tokyo", "Shibuya", "Shinjuku"],
            "Kyoto": ["Kyoto", "Uji"],
            "Osaka": ["Osaka", "Kobe", "Sakai"],
            "Yokohama": ["Yokohama", "Kamakura"],
        },
        "China": {
            "Beijing": ["Beijing"],
            "Shanghai": ["Shanghai"],
            "Guangdong": ["Guangzhou", "Shenzhen", "Foshan"],
            "Zhejiang": ["Hangzhou", "Ningbo"],
        },
        "Mexico": {
            "Mexico City": ["Mexico City"],
            "State of Mexico": ["Ecatepec", "Naucalpan"],
            "Jalisco": ["Guadalajara", "Zapopan"],
            "Nuevo Len": ["Monterrey", "San Pedro Garza Garca"],
        },
        "Brazil": {
            "So Paulo": ["So Paulo", "Campinas", "Santos"],
            "Rio de Janeiro": ["Rio de Janeiro", "Niteri"],
            "Minas Gerais": ["Belo Horizonte", "Uberlndia"],
            "Bahia": ["Salvador", "Feira de Santana"],
        },
        "South Africa": {
            "Gauteng": ["Johannesburg", "Pretoria", "Soweto"],
            "Western Cape": ["Cape Town", "Stellenbosch"],
            "KwaZulu-Natal": ["Durban", "Pietermaritzburg"],
        },
        "Singapore": {
            "Singapore": ["Singapore", "Marina Bay", "Orchard"],
        },
        "New Zealand": {
            "Auckland": ["Auckland", "Manukau"],
            "Wellington": ["Wellington", "Lower Hutt"],
            "Canterbury": ["Christchurch", "Timaru"],
        },
    }


# ===================== CHAT CONSTANTS =====================

EMPATHETIC_GREETINGS = [
    "Hello! I'm here to listen and support you. How are you feeling today?",
    "Welcome! I'm genuinely glad you're here. How has your day been so far?",
    "Hi there! I'm your companion on this journey. What's on your mind today?",
    "Hello! It takes courage to reach out. How are you doing right now?",
    "Welcome back! I'm happy to see you. What's been on your heart lately?",
    "Hi! I'm here to support you through whatever you're experiencing. How can I help?",
]


# ===================== PAGE: LOADING =====================
def show_loading_page():
    """Loading page with animation"""
    st.markdown("""
    <div class="loading-container">
        <h1 class="loading-text">Mental Wellbeing</h1>
    </div>
    """, unsafe_allow_html=True)
    
    time.sleep(1.0)
    st.session_state.page = "welcome"
    st.rerun()


# ===================== PAGE: WELCOME =====================
def show_welcome_page():
    """Welcome/Hero page"""
    st.markdown("""
    <style>
    .welcome-transparent {
        background: rgba(15, 12, 41, 0.1);
        backdrop-filter: blur(5px);
        border: 1px solid rgba(82, 113, 255, 0.1);
        border-radius: 20px;
        padding: 60px 40px;
        max-width: 900px;
        margin: 0 auto;
        text-align: center;
    }
    </style>
    <div class="welcome-transparent">
        <p style='color: #FFFFFF; font-size: 1.5rem; margin-bottom: 0; text-shadow: 0 2px 10px rgba(0,0,0,0.5);'>Welcome to</p>
        <h1 style='color: #FFFFFF; font-size: 5rem; font-weight: 900; margin-top: 0; text-shadow: 0 4px 15px rgba(82, 113, 255, 0.6);'>Mental Wellbeing</h1>
        <p style='color: #E0E0FF; font-size: 1.4rem; max-width: 800px; font-weight: 500; text-shadow: 0 2px 10px rgba(0,0,0,0.5); margin: 20px auto 0;'>
            Let's work together to make you feel stress free and more productive each day.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1.5, 0.5, 1.5])
    with col2:
        if st.button("Continue", use_container_width=True, key="welcome_continue"):
            st.session_state.page = "auth_choice"
            st.rerun()
            
    st.markdown("""
    <div class="disclaimer">
        By continuing, I confirm I am 12 or older and accept the Terms of Service
    </div>
    """, unsafe_allow_html=True)


# ===================== PAGE: AUTH CHOICE =====================
def show_auth_choice():
    """Login/Signup choice page"""
    st.markdown("""
    <div class="choice-wrapper">
        <p style='color:#4B0082; font-size:2.2rem; font-weight:800; font-style:italic;'>
            "The secret of getting ahead is getting started."
        </p>
        <p style='color:#6A5B9D; font-size:1.2rem; margin-bottom:40px;'>
            Ready to transform your routine?
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1.1, 0.8, 1.1])
    with col2:
        if st.button("Create New Account", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()

    col1, col2, col3 = st.columns([1.1, 0.8, 1.1])
    with col2:
        if st.button("I already have an account", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()




# ===================== PAGE: LOGIN =====================
def show_login_page():
    """Login page — two methods: Mobile + OTP  |  Email + Password"""

    st.markdown("""
    <style>
    .login-form {
        border: 1.5px solid rgba(82, 113, 255, 0.4);
        border-radius: 25px;
        padding: 45px 50px 35px 50px;
        max-width: 500px;
        margin: 0 auto;
        text-align: center;
    }
    .form-title {
        color: #FFFFFF;
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 6px;
        text-shadow: 0 2px 10px rgba(82, 113, 255, 0.5);
    }
    .form-subtitle {
        color: #B0C4FF;
        font-size: 0.97rem;
        margin-bottom: 24px;
    }
    /* Style the tab bar to look more polished */
    div[data-baseweb="tab-list"] {
        background: rgba(82, 113, 255, 0.08) !important;
        border-radius: 12px !important;
        padding: 4px !important;
        gap: 4px !important;
    }
    div[data-baseweb="tab"] {
        border-radius: 9px !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("""
        <div class="login-form">
            <div class="form-title">Welcome Back</div>
            <div class="form-subtitle">Sign in to your Mental Wellbeing account</div>
        """, unsafe_allow_html=True)

        tab_otp, tab_email = st.tabs(["📱  Mobile & OTP", "✉️  Email & Password"])

        # ── TAB 1: Mobile + OTP ──────────────────────────────────────────────
        with tab_otp:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            c_mob, c_otp_btn = st.columns([2, 1])
            with c_mob:
                mob = st.text_input(
                    "Registered Mobile Number",
                    placeholder="e.g. 9876543210",
                    key="login_mob",
                )
            with c_otp_btn:
                st.markdown("<div style='padding-top:28px;'></div>", unsafe_allow_html=True)
                if st.button("Get OTP", use_container_width=True, key="login_get_otp"):
                    otp_times = st.session_state.get("_otp_times", [])
                    now_ts = time.time()
                    otp_times = [t for t in otp_times if now_ts - t < 600]
                    if len(otp_times) >= 5:
                        st.warning("Too many OTP requests. Please wait a few minutes.")
                    elif len(mob) == 10:
                        with st.spinner("Checking..."):
                            user = verify_user_login(mob)
                            if user:
                                st.session_state.login_otp = str(random.randint(100000, 999999))
                                st.session_state.login_user = user
                                otp_times.append(now_ts)
                                st.session_state["_otp_times"] = otp_times
                                st.toast("OTP sent to your registered number!")
                                if DEMO_MODE:
                                    st.info(f"[Demo] OTP: {st.session_state.login_otp}")
                            else:
                                st.error("Mobile number not found. Please Sign Up.")
                    else:
                        st.warning("Enter a valid 10-digit mobile number.")

            otp_input = st.text_input(
                "Enter 6-digit OTP",
                placeholder="XXXXXX",
                type="password",
                key="login_otp_input",
            )

            if st.button("Sign In with OTP", use_container_width=True, key="login_submit_otp"):
                if not mob:
                    st.warning("Please enter your mobile number and request an OTP.")
                elif otp_input == st.session_state.get("login_otp"):
                    u_id, u_fullname, u_username = st.session_state.login_user
                    st.session_state.current_uid = u_id
                    st.session_state.user_name = u_fullname
                    st.session_state.username = u_username
                    st.session_state.session_id = str(uuid.uuid4())
                    st.session_state.page = "chat"
                    st.success("Verified! Welcome back.")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Invalid OTP. Please try again.")

        # ── TAB 2: Email + Password ──────────────────────────────────────────
        with tab_email:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            login_email = st.text_input(
                "Email Address",
                placeholder="e.g. alex@example.com",
                key="login_email",
            )
            login_password = st.text_input(
                "Password",
                placeholder="Your password",
                type="password",
                key="login_password",
            )

            if st.button("Sign In with Email", use_container_width=True, key="login_submit_email"):
                if not login_email or not login_password:
                    st.warning("Please enter both email and password.")
                else:
                    with st.spinner("Authenticating..."):
                        user = verify_user_email_password(login_email, login_password)
                    if user:
                        u_id, u_fullname, u_username = user
                        st.session_state.current_uid = u_id
                        st.session_state.user_name = u_fullname
                        st.session_state.username = u_username
                        st.session_state.session_id = str(uuid.uuid4())
                        st.session_state.page = "chat"
                        st.success("Verified! Welcome back.")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Incorrect email or password.")

        st.markdown("<hr style='border: 1px solid rgba(82, 113, 255, 0.3); margin: 25px 0;'>", unsafe_allow_html=True)
        st.markdown(
            "<p style='color: #B0C4FF; text-align: center; font-size: 0.95rem; margin: 15px 0;'>"
            "Don't have an account?</p>",
            unsafe_allow_html=True,
        )

        col_signup1, col_signup2, col_signup3 = st.columns([0.5, 2, 0.5])
        with col_signup2:
            if st.button("Create Account", use_container_width=True, key="login_to_signup"):
                st.session_state.page = "signup"
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ===================== PAGE: SIGNUP =====================
def _validate_signup(u_name, f_name, mobile, pin, email, password, confirm_password):
    """Validate signup form fields. Returns error message or None."""
    if not u_name or len(u_name.strip()) < 3:
        return "Username must be at least 3 characters."
    if not re.match(r'^[a-zA-Z0-9_]+$', u_name.strip()):
        return "Username must be alphanumeric (letters, numbers, underscores)."
    if not f_name or len(f_name.strip()) < 2:
        return "Full name is required."
    if not mobile or not re.match(r'^\d{10}$', mobile.strip()):
        return "Mobile number must be exactly 10 digits."
    if pin and not re.match(r'^\d{4,10}$', pin.strip()):
        return "Pincode must be 4-10 digits."
    if not email or not re.match(r'^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$', email.strip()):
        return "Please enter a valid email address."
    if not password or len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one number."
    if password != confirm_password:
        return "Passwords do not match."
    return None


def show_signup_page():
    """Signup page with demographic + 12-step onboarding"""
    st.markdown("""
        <style>
        /* Premium Signup Styling */
        .signup-container {
            max-width: 700px;
            margin: 0 auto;
            width: 100%;
        }

        .signup-header {
            text-align: center;
            margin-bottom: 40px;
            padding-top: 20px;
            width: 100%;
        }

        .form-title {
            color: #FFFFFF;
            font-size: 3rem;
            font-weight: 900;
            margin-bottom: 15px;
            background: linear-gradient(135deg, #5271FF 0%, #8A2BE2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-shadow: 0 2px 10px rgba(82, 113, 255, 0.3);
        }

        .form-subtitle {
            color: #B0C4FF;
            font-size: 1.1rem;
            margin-bottom: 20px;
            font-weight: 500;
        }

        .signup-form {
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .form-section-title {
            color: #B0C4FF;
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 25px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(82, 113, 255, 0.2);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .form-section-title:first-of-type {
            margin-top: 0;
        }

        /* Input field styling */
        input[type="text"], input[type="password"], input[type="email"], input[type="date"] {
            background-color: rgba(30, 20, 60, 0.6) !important;
            border: 1.5px solid rgba(82, 113, 255, 0.4) !important;
            color: #FFFFFF !important;
            border-radius: 10px !important;
        }

        input[type="text"]::placeholder, input[type="password"]::placeholder, input[type="email"]::placeholder {
            color: rgba(255, 255, 255, 0.35) !important;
        }

        input[type="text"]:focus, input[type="password"]:focus, input[type="email"]:focus, input[type="date"]:focus {
            background-color: rgba(50, 40, 100, 0.5) !important;
            border: 1.5px solid rgba(82, 113, 255, 0.8) !important;
            box-shadow: 0 0 10px rgba(82, 113, 255, 0.3) !important;
        }

        .password-strength {
            height: 4px;
            border-radius: 2px;
            margin-top: 8px;
            background: rgba(255, 255, 255, 0.1);
            overflow: hidden;
        }

        .password-strength-bar {
            height: 100%;
            border-radius: 2px;
            transition: all 0.3s ease;
        }

        .strength-weak { background: #FF6B6B; }
        .strength-fair { background: #FFA500; }
        .strength-good { background: #FFD700; }
        .strength-strong { background: #00DD77; }

        .strength-text {
            font-size: 0.75rem;
            margin-top: 5px;
            color: #B0C4FF;
        }

        .input-group {
            margin-bottom: 18px;
        }

        .input-label {
            color: #B0C4FF;
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 8px;
            display: block;
        }

        .input-icon {
            font-size: 1.1rem;
            margin-right: 8px;
        }

        /* Selectbox styling */
        [data-baseweb="select"] {
            border-radius: 10px !important;
        }

        [data-baseweb="select"] option {
            color: #000000 !important;
            background-color: #FFFFFF !important;
        }

        [data-baseweb="select"] > div {
            background-color: rgba(30, 20, 60, 0.6) !important;
            color: #FFFFFF !important;
            border: 1.5px solid rgba(82, 113, 255, 0.4) !important;
            border-radius: 10px !important;
        }

        [data-baseweb="select"] > div > div {
            background-color: rgba(30, 20, 60, 0.6) !important;
            color: #FFFFFF !important;
        }

        [data-baseweb="select"]:hover > div {
            background-color: rgba(50, 40, 100, 0.5) !important;
            border: 1.5px solid rgba(82, 113, 255, 0.6) !important;
        }

        [data-baseweb="popover"] {
            background-color: rgba(30, 20, 60, 0.9) !important;
        }

        .checkbox-custom {
            color: #B0C4FF;
            font-size: 0.9rem;
        }

        .btn-register {
            background: linear-gradient(135deg, #5271FF 0%, #8A2BE2 100%) !important;
            font-size: 1.05rem !important;
            font-weight: 700 !important;
            padding: 12px !important;
            margin-top: 20px !important;
            border: none !important;
            border-radius: 15px !important;
            color: white !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 4px 15px rgba(82, 113, 255, 0.3) !important;
        }

        .btn-register:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(82, 113, 255, 0.5) !important;
        }

        .otp-section {
            background: rgba(82, 113, 255, 0.1);
            border-left: 3px solid #5271FF;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 18px;
        }

        .privacy-notice {
            background: rgba(82, 113, 255, 0.08);
            border: 1px solid rgba(82, 113, 255, 0.2);
            border-radius: 12px;
            padding: 15px;
            margin: 25px 0;
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.8);
            line-height: 1.6;
            text-align: center;
        }

        .checkbox-wrapper {
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 20px 0;
        }

        .checkbox-wrapper label {
            color: #B0C4FF !important;
            font-size: 0.9rem !important;
        }

        .btn-container {
            display: flex;
            justify-content: center;
            margin: 25px 0;
        }

        .login-link {
            text-align: center;
            margin-top: 30px;
            color: rgba(255, 255, 255, 0.7);
            padding: 20px 0;
        }

        .login-link p {
            margin: 0;
            line-height: 1.6;
        }

        .login-link a {
            color: #5271FF;
            text-decoration: none;
            font-weight: 600;
        }

        .login-link a:hover {
            text-decoration: underline;
        }
        </style>
    """, unsafe_allow_html=True)

    # PHASE 1: REGISTRATION
    if st.session_state.current_uid is None:
        # Load geolocation data
        LOCATION_DATA = load_geolocation_data()

        # Calculate date range: 150 years old to 10 years back from now
        today = datetime.now()
        min_date = today - timedelta(days=365*150)  # 150 years ago
        max_date = today - timedelta(days=365*10)   # 10 years ago

        # Premium Signup Header
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            <div class="signup-header">
                <div class="form-title">Create Account</div>
                <div class="form-subtitle">Your Personal Mental Wellness Companion</div>
            </div>
            """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            st.markdown('<div class="signup-form">', unsafe_allow_html=True)

            # ===== ACCOUNT SECTION =====
            st.markdown('<div class="form-section-title">👤 Account Information</div>', unsafe_allow_html=True)

            u_name = st.text_input("Username", placeholder="e.g. sunny_vibes", key="signup_u_name")
            f_name = st.text_input("Full Name", placeholder="e.g. Alex Johnson", key="signup_f_name")
            email_val = st.text_input("Email Address", placeholder="e.g. alex@example.com", key="signup_email")

            # Role Selection
            role = st.selectbox("Role", ["Patient", "Doctor"], index=None, key="signup_role", placeholder="Select your role")

            # ===== SECURITY SECTION =====
            st.markdown('<div class="form-section-title">🔐 Security</div>', unsafe_allow_html=True)

            password_val = st.text_input(
                "Password", placeholder="Min 8 chars, 1 uppercase, 1 number",
                type="password", key="signup_password"
            )

            # Password Strength Indicator
            if password_val:
                strength = 0
                strength_text = "Weak"
                strength_class = "strength-weak"

                if len(password_val) >= 8:
                    strength += 1
                if any(c.isupper() for c in password_val):
                    strength += 1
                if any(c.isdigit() for c in password_val):
                    strength += 1
                if len(password_val) >= 12:
                    strength += 1
                if any(c in "!@#$%^&*" for c in password_val):
                    strength += 1

                if strength <= 1:
                    strength_text = "Weak"
                    strength_class = "strength-weak"
                elif strength <= 2:
                    strength_text = "Fair"
                    strength_class = "strength-fair"
                elif strength <= 3:
                    strength_text = "Good"
                    strength_class = "strength-good"
                else:
                    strength_text = "Strong"
                    strength_class = "strength-strong"

                st.markdown(f"""
                <div class="password-strength">
                    <div class="password-strength-bar {strength_class}" style="width: {(strength/5)*100}%;"></div>
                </div>
                <div class="strength-text">Strength: <strong>{strength_text}</strong></div>
                """, unsafe_allow_html=True)

            confirm_pw_val = st.text_input(
                "Confirm Password", placeholder="Re-enter password",
                type="password", key="signup_confirm_password"
            )

            # ===== PERSONAL INFORMATION SECTION =====
            st.markdown('<div class="form-section-title">📋 Personal Information</div>', unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                dob = st.date_input("Date of Birth", value=None, min_value=min_date, max_value=max_date, key="signup_dob")
            with c2:
                gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"], index=None, key="signup_gender")

            # ===== LOCATION SECTION =====
            st.markdown('<div class="form-section-title">📍 Location</div>', unsafe_allow_html=True)

            # Country Selection
            countries_list = sorted(list(LOCATION_DATA.keys()))
            country = st.selectbox("Country", countries_list, index=0, key="signup_country")

            # State Selection (dynamic based on country)
            states = sorted(list(LOCATION_DATA[country].keys())) if country in LOCATION_DATA else []
            state = st.selectbox("State", states, index=0, key="signup_state") if states else ""

            # City Selection (dynamic based on state)
            cities = sorted(LOCATION_DATA[country][state]) if state and state in LOCATION_DATA[country] else []
            city = st.selectbox("City", cities, index=0, key="signup_city") if cities else ""

            pin = st.text_input("Pincode", placeholder="e.g. 400001", key="signup_pin")

            # ===== CONTACT & VERIFICATION SECTION =====
            st.markdown('<div class="form-section-title">📞 Contact & Verification</div>', unsafe_allow_html=True)

            # Mobile and OTP side by side
            c_mob, c_otp = st.columns([2, 1])
            with c_mob:
                mobile = st.text_input("Mobile Number", placeholder="10 Digits", key="signup_mobile")
            with c_otp:
                st.markdown("<div style='padding-top:8px;'></div>", unsafe_allow_html=True)
                if st.button("Get OTP", key="signup_get_otp", use_container_width=True):
                    # P2 #17: OTP rate limiting — max 5 per 10 min
                    otp_times = st.session_state.get("_otp_times", [])
                    now_ts = time.time()
                    otp_times = [t for t in otp_times if now_ts - t < 600]
                    if len(otp_times) >= 5:
                        st.warning("Too many OTP requests. Please wait a few minutes.")
                    elif len(mobile) == 10:
                        st.session_state.signup_otp = str(random.randint(100000, 999999))
                        otp_times.append(now_ts)
                        st.session_state["_otp_times"] = otp_times
                        st.toast("✅ OTP sent to your phone!")
                        if DEMO_MODE:
                            st.info(f"**[Demo Mode]** OTP: `{st.session_state.signup_otp}`")
                    else:
                        st.error("❌ Enter 10-digit mobile number")

            otp_in = st.text_input("Enter OTP", placeholder="Verification Code (6 digits)", key="signup_otp_input")

            # Privacy & Agreement
            st.markdown("""
            <div class="privacy-notice">
                <strong>🔒 Your Privacy Matters</strong><br>
                Your data is encrypted and secure. We never share your information without consent.
                By signing up, you agree to our privacy policy and terms of use.
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="checkbox-wrapper">', unsafe_allow_html=True)
            agree = st.checkbox("I agree to the privacy policy and terms of use", key="signup_agree", help="Required to create account")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="btn-container">', unsafe_allow_html=True)
            if st.button("🚀 Complete Registration", key="signup_register", use_container_width=True, help="Finish creating your account"):
                if otp_in == st.session_state.get('signup_otp') and agree:
                    val_err = _validate_signup(u_name, f_name, mobile, pin, email_val, password_val, confirm_pw_val)
                    if val_err:
                        st.warning(val_err)
                    else:
                        u_id = register_user({
                            'username': u_name, 'full_name': f_name, 'dob': dob,
                            'gender': gender, 'role': role, 'country': country, 'state': state,
                            'city': city, 'pincode': pin, 'mobile': mobile,
                            'email': email_val.strip().lower(), 'password': password_val,
                        })

                        if u_id == "EXISTS":
                            st.error("Username or Mobile already registered.")
                        elif u_id:
                            st.session_state.current_uid = u_id
                            st.session_state.user_name = f_name
                            st.session_state.user_role = role
                            st.session_state.show_welcome = True
                            st.success("Account Created!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Database connection error.")
                else:
                    st.warning("Please verify OTP and agree to terms.")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("""
            <div class="login-link">
                <p>Already have an account?</p>
                <p style="font-size: 0.9rem; color: rgba(255, 255, 255, 0.6);">Click the button below to sign in</p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="btn-container">', unsafe_allow_html=True)
            if st.button("👤 Login to Account", use_container_width=True, key="signup_to_login", help="Return to login page"):
                st.session_state.page = "login"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

    # PHASE 2: WELCOME TRANSITION
    elif st.session_state.show_welcome:
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            st.markdown(f"""
                <div class="signup-form" style='text-align: center;'>
                    <h1 style='color:#FFFFFF; margin-bottom:20px;'>Welcome, {safe_html(st.session_state.user_name)}! &#127881;</h1>
                    <p style='color:#B0C4FF; font-size:1.1rem; margin:0;'>Your account is ready. To provide the best support, we need to understand a bit more about your daily life.</p>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Begin Profile Setup", key="signup_begin_onboard", use_container_width=True):
                st.session_state.show_welcome = False
                st.session_state.onboard_step = 1
                st.session_state.ans = []
                st.rerun()

    # PHASE 3: 12-STEP ONBOARDING
    else:
        step = st.session_state.onboard_step
        
        questions = [
            {"q": "How would you describe your current role?", "opts": ["Student", "Working full-time", "Working part-time", "Self-employed", "Unemployed", "Homemaker", "Retired"]},
            {"q": "What best describes your daily routine?", "opts": ["Highly structured", "Somewhat structured", "Flexible", "Irregular", "Very chaotic"]},
            {"q": "How has your sleep been recently?", "opts": ["Restful and regular", "Mostly okay", "Irregular", "Poor", "Very poor"]},
            {"q": "How easy is it for you to focus on tasks?", "opts": ["Very easy", "Mostly easy", "Sometimes difficult", "Often difficult", "Very difficult"]},
            {"q": "How supported do you currently feel in your life?", "opts": ["Very supported", "Moderately supported", "Slightly supported", "Not supported"]},
            {"q": "Have you experienced significant life changes recently?", "opts": ["Yes (last 3 months)", "Yes (within 1 year)", "Minor changes", "No changes"]},
            {"q": "How comfortable are you with asking for help?", "opts": ["Very comfortable", "Somewhat comfortable", "Uncomfortable", "Very uncomfortable"]},
            {"q": "What currently causes you the most stress?", "opts": ["Work/Studies", "Relationships", "Family/Home", "Finances", "Health", "Future Uncertainty"]},
            {"q": "How often do you feel mentally exhausted?", "opts": ["Never", "Rarely", "Sometimes", "Often", "Almost always"]},
            {"q": "Do you engage in mindfulness or relaxation practices?", "opts": ["Regularly", "Sometimes", "Rarely", "Tried before", "Never"]},
            {"q": "What are you hoping to gain from using this app?", "opts": ["Reduce Stress", "Improve Mood", "Better Focus", "Understand Emotions", "Ongoing Support"]},
            {"q": "When feeling low or stressed, what do you do first?", "opts": ["Talk to someone", "Handle on my own", "Distract myself", "Avoid/Suppress", "Not sure"]},
        ]
        
        q_data = questions[step-1]

        # Onboarding-specific CSS
        st.markdown("""
        <style>
        .onboard-container {
            background: rgba(15, 12, 41, 0.4);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 20px;
            padding: 30px 40px;
            max-width: 800px;
            margin: 20px auto;
        }
        .onboard-progress {
            text-align: left;
            font-size: 0.9rem;
            color: rgba(255, 255, 255, 0.6);
            margin-bottom: 8px;
        }
        .onboard-question {
            text-align: left;
            font-size: 1.5rem;
            font-weight: 700;
            color: #FFFFFF;
            margin-bottom: 20px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        /* Radio button styling - COLUMN layout, one option per row */
        div[data-testid="stRadio"] > div {
            display: flex !important;
            flex-direction: column !important;
            gap: 10px !important;
        }
        div[data-testid="stRadio"] label {
            background: rgba(255, 255, 255, 0.05) !important;
            border: 1px solid rgba(255, 255, 255, 0.25) !important;
            border-radius: 12px !important;
            padding: 14px 20px !important;
            color: rgba(255, 255, 255, 0.9) !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            width: 100% !important;
            text-align: left !important;
            margin: 0 !important;
            font-size: 1rem !important;
        }
        div[data-testid="stRadio"] label:hover {
            background: rgba(255, 255, 255, 0.1) !important;
            border-color: rgba(255, 255, 255, 0.5) !important;
        }
        div[data-testid="stRadio"] label[data-checked="true"],
        div[data-testid="stRadio"] input:checked + label {
            background: rgba(255, 255, 255, 0.15) !important;
            border-color: rgba(255, 255, 255, 0.6) !important;
        }
        .nav-btn-center {
            display: flex;
            justify-content: center;
            margin-top: 25px;
        }
        .nav-btn-row {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-top: 25px;
        }
        </style>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([0.5, 3, 0.5])
        with col2:
            st.markdown(f"""
            <div class="onboard-container">
                <div class="onboard-progress">Step {step} of 12  {int((step/12)*100)}% complete</div>
                <div class="onboard-question">{q_data['q']}</div>
            </div>
            """, unsafe_allow_html=True)

            # Progress bar
            st.progress(step / 12)

            # Radio buttons for options
            choice = st.radio(
                "Select one:",
                q_data['opts'],
                index=None,
                key=f"onboard_radio_{step}",
                label_visibility="collapsed",
                horizontal=False
            )
            
            # Navigation buttons
            if step == 1:
                # First step: Only Next button, centered
                col_a, col_b, col_c = st.columns([1.5, 1, 1.5])
                with col_b:
                    if st.button("Next ", key=f"next_{step}", use_container_width=True):
                        if choice:
                            st.session_state.ans.append(choice)
                            st.session_state.onboard_step += 1
                            st.rerun()
                        else:
                            st.warning(" Please select an option.")
            else:
                # Other steps: Back and Next side by side
                col_a, col_b, col_c, col_d, col_e = st.columns([1, 0.8, 0.2, 0.8, 1])
                with col_b:
                    if st.button(" Back", key=f"prev_{step}", use_container_width=True):
                        st.session_state.onboard_step -= 1
                        if st.session_state.ans:
                            st.session_state.ans.pop()
                        st.rerun()
                with col_d:
                    btn_text = "Next " if step < 12 else "Finish "
                    if st.button(btn_text, key=f"next_{step}", use_container_width=True):
                        if choice:
                            st.session_state.ans.append(choice)
                            if step < 12:
                                st.session_state.onboard_step += 1
                                st.rerun()
                            else:
                                with st.spinner("Saving profile..."):
                                    q_list = [q['q'] for q in questions]
                                    success = save_onboarding(st.session_state.current_uid, q_list, st.session_state.ans)
                                    if success:
                                        update_verification(st.session_state.current_uid)
                                        st.balloons()
                                        # Move to trusted adult form
                                        st.session_state.page = "trusted_adult_form"
                                        st.rerun()
                                    else:
                                        st.error(" Error saving profile.")
                        else:
                            st.warning(" Please select an option.")


# ===================== PAGE: TRUSTED ADULT FORM (AFTER ONBOARDING) =====================
def show_trusted_adult_form():
    """Form to collect trusted adult info after onboarding completes."""
    st.set_page_config(page_title="Trusted Adult - MindWell", layout="centered")

    col1, col2, col3 = st.columns([0.5, 3, 0.5])
    with col2:
        st.markdown("""
        <style>
        .trusted-adult-container {
            background: rgba(15, 12, 41, 0.4);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 20px;
            padding: 40px;
            max-width: 600px;
            margin: 40px auto;
        }
        .trusted-adult-title {
            text-align: center;
            font-size: 2rem;
            font-weight: 700;
            color: #FFFFFF;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .trusted-adult-subtitle {
            text-align: center;
            font-size: 1rem;
            color: rgba(255, 255, 255, 0.8);
            margin-bottom: 30px;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="trusted-adult-container">
            <div class="trusted-adult-title">👥 Trusted Adult</div>
            <div class="trusted-adult-subtitle">Help us support you better during difficult times</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("trusted_adult_onboarding_form"):
            st.write("During a crisis, we can reach out to this person to help support you.")

            trusted_name = st.text_input(
                "Trusted Adult Name *",
                placeholder="e.g., Mom, Dad, Counselor",
                key="trusted_name_onboarding"
            )

            trusted_phone = st.text_input(
                "Trusted Adult Phone Number *",
                placeholder="+91 XXXXX XXXXX",
                key="trusted_phone_onboarding"
            )

            col_a, col_b, col_c = st.columns([1, 1, 1])
            with col_b:
                submitted = st.form_submit_button("Continue", use_container_width=True)

            if submitted:
                if trusted_name and trusted_phone:
                    # Save to database
                    from database import save_trusted_adult_info
                    success = save_trusted_adult_info(
                        st.session_state.current_uid,
                        trusted_name,
                        trusted_phone
                    )
                    if success:
                        st.session_state.onboarding_profile["trusted_adult_name"] = trusted_name
                        st.session_state.onboarding_profile["trusted_adult_phone"] = trusted_phone
                        st.balloons()
                        st.session_state.session_id = str(uuid.uuid4())
                        time.sleep(0.5)
                        st.session_state.page = "chat"
                        st.rerun()
                    else:
                        st.error("Failed to save. Please try again.")
                else:
                    st.warning("⚠️ Please fill in both fields to continue.")

        # Skip option
        st.write("")
        if st.button("Skip for now", use_container_width=True, key="skip_trusted_adult"):
            st.session_state.session_id = str(uuid.uuid4())
            time.sleep(0.5)
            st.session_state.page = "chat"
            st.rerun()


# ===================== PAGE: CHAT (MAIN APPLICATION) =====================
def show_chatbot():
    """Advanced multi-agent chat interface with fixed header, input, and empathetic greeting"""
    
    user_id = st.session_state.get('current_uid')
    user_name = st.session_state.get('user_name', 'Guest')

    try:
        query_params = st.query_params
    except Exception:
        query_params = {}
    if "session_id" in query_params:
        restored_session = query_params["session_id"]
        for attempt in (1, 2):
            with get_pooled_connection() as conn:
                if not conn:
                    break
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM chat_messages WHERE user_id = %s AND session_id = %s",
                        (user_id, restored_session),
                    )
                    if cur.fetchone()[0] > 0:
                        st.session_state.session_id = restored_session
                    break
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                    if attempt == 1:
                        logger.warning("Session restore query failed (stale connection, retrying once): %s", e)
                        continue
                    logger.warning("Session restore query failed (stale connection): %s", e)
                    break
                finally:
                    cur.close()
    
    # Session state initialization
    if 'session_id' not in st.session_state or not st.session_state.get("session_id"):
        recent_session = _get_recent_session_id(user_id)
        st.session_state.session_id = recent_session or str(uuid.uuid4())
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'chat_title' not in st.session_state:
        st.session_state.chat_title = "New Conversation"

    # Ensure URL reflects the active session.
    st.query_params["session_id"] = st.session_state.session_id
    if not st.session_state.messages and st.session_state.session_id:
        try:
            st.session_state.messages = load_specific_session(user_id, st.session_state.session_id)
        except Exception:
            st.session_state.messages = []
    if user_id:
        # Recover any stale sessions whose timer may have been missed
        # (for example after app/tab restart) so summaries are generated.
        _finalize_due_sessions(
            user_id,
            idle_minutes=SESSION_IDLE_MINUTES,
            limit=5,
        )
    if user_id and st.session_state.session_id:
        _schedule_session_finalization(user_id, st.session_state.session_id, idle_minutes=SESSION_IDLE_MINUTES)
    
    # --- MAIN CSS STYLING ---
    st.markdown(f"""
        <style>
        /* Font already loaded by styles.py */
        
        * {{ font-family: 'Inter', sans-serif; }}
        
        .stApp {{
            color: #FFFFFF !important;
        }}
        
        /* Keep Streamlit header visible - only hide footer */
        footer {{visibility: hidden;}}
        
        /* Sidebar styling with fixed sections */
        [data-testid="stSidebar"] {{
            background: rgba(15, 12, 41, 0.95) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        [data-testid="stSidebar"] > div:first-child {{
            display: flex;
            flex-direction: column;
            height: 100vh;
        }}
        
        /* Scrollable section for recent chats */
        .sidebar-scroll {{
            flex: 1;
            overflow-y: auto;
            padding-right: 5px;
            max-height: calc(100vh - 280px);
        }}
        
        .sidebar-scroll::-webkit-scrollbar {{
            width: 4px;
        }}
        
        .sidebar-scroll::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.05);
        }}
        
        .sidebar-scroll::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.2);
            border-radius: 4px;
        }}
        
        /* Fixed bottom section for theme and logout */
        .sidebar-fixed-bottom {{
            position: sticky;
            bottom: 0;
            background: rgba(15, 12, 41, 0.98);
            padding: 10px 0;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        /* Top header bar - beside sidebar, flexible positioning */
        /* Top header bar - sticky and flexible */
        .chat-header {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(15, 12, 41, 0.85);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding: 15px 30px;
            margin-bottom: 20px;
            border-radius: 0 0 20px 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
        }}
        
        .chat-header-title {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #FFFFFF;
            text-align: center;
        }}
        
        .chat-header-profile {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: linear-gradient(135deg, #5271FF, #8E8EFF);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 0.9rem;
            color: white;
            position: absolute;
            right: 30px;
        }}
        
        /* Chat messages area */
        .chat-messages {{
            padding: 0 20px;
            padding-bottom: 120px;
        }}
        
        /* User message: Right-aligned */
        .user-msg-wrap {{
            display: flex;
            justify-content: flex-end;
            margin-bottom: 15px;
        }}
        
        .user-msg {{
            background: linear-gradient(135deg, #6a11cb, #2575fc);
            padding: 12px 18px;
            border-radius: 18px 18px 4px 18px;
            max-width: 65%;
            color: white;
            line-height: 1.5;
            box-shadow: 0 3px 12px rgba(106, 17, 203, 0.3);
        }}
        
        /* Bot message: Left-aligned */
        .bot-msg-wrap {{
            display: flex;
            justify-content: flex-start;
            margin-bottom: 15px;
        }}
        
        .bot-msg {{
            background: rgba(255, 255, 255, 0.1);
            padding: 12px 18px;
            border-radius: 18px 18px 18px 4px;
            max-width: 65%;
            color: #f0f0f0;
            line-height: 1.5;
            border: 1px solid rgba(255, 255, 255, 0.15);
        }}
        
        /* Streamlit chat_input styling - FIXED at bottom center */
        [data-testid="stChatInput"] {{
            position: fixed !important;
            bottom: 20px !important;
            left: max(320px, 25%) !important;
            right: 20px !important;
            max-width: 800px !important;
            margin: 0 auto !important;
            z-index: 1000 !important;
        }}
        
        [data-testid="stChatInput"] > div {{
            background: rgba(25, 22, 50, 0.95) !important;
            border: 1.5px solid rgba(100, 130, 200, 0.4) !important;
            border-radius: 28px !important;
            backdrop-filter: blur(15px) !important;
            box-shadow: 0 4px 25px rgba(0, 0, 0, 0.4) !important;
        }}
        
        [data-testid="stChatInput"] textarea {{
            background: transparent !important;
            color: rgba(255, 255, 255, 0.95) !important;
            font-size: 1rem !important;
            padding: 12px 20px !important;
        }}
        
        [data-testid="stChatInput"] textarea::placeholder {{
            color: rgba(150, 180, 220, 0.7) !important;
        }}
        
        [data-testid="stChatInput"] button {{
            background: linear-gradient(135deg, rgba(82, 113, 255, 0.6), rgba(130, 160, 220, 0.5)) !important;
            border-radius: 50% !important;
            border: none !important;
        }}
        
        [data-testid="stChatInput"] button:hover {{
            background: linear-gradient(135deg, rgba(82, 113, 255, 0.8), rgba(130, 160, 220, 0.7)) !important;
            transform: scale(1.05) !important;
        }}
        
        /* Override Streamlit text input styling */
        [data-testid="stTextInput"] > div > div > input {{
            background: transparent !important;
            border: none !important;
            color: rgba(255, 255, 255, 0.9) !important;
            caret-color: #8ea8ff !important;
        }}
        
        /* Button styling */
        .stButton button {{
            background: rgba(255, 255, 255, 0.08) !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            color: #FFFFFF !important;
            border-radius: 10px !important;
            transition: all 0.2s ease !important;
        }}
        
        .stButton button:hover {{
            background: rgba(255, 255, 255, 0.15) !important;
            border-color: rgba(255, 255, 255, 0.3) !important;
        }}
        </style>
    """, unsafe_allow_html=True)

    # --- SIDEBAR ---
    with st.sidebar:
        # Title
        st.markdown("### Mental Wellbeing")

        # New Chat Button
        if st.button("New Chat", use_container_width=True, key="new_chat"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.chat_title = "New Conversation"
            st.query_params["session_id"] = st.session_state.session_id
            st.rerun()

        # Divider below New Chat
        st.markdown("---")
        
        st.markdown("**Recent Chats**")
        
        # Left-align chat buttons
        st.markdown('<style>.sidebar-chat-btn button {text-align: left !important; justify-content: flex-start !important;}</style>', unsafe_allow_html=True)
        
        # Scrollable container for recent chats
        st.markdown('<div class="sidebar-scroll sidebar-chat-btn">', unsafe_allow_html=True)
        
        # Load recent chats with cached summaries (#9, #17)
        try:
            chats = _load_sidebar_chats(user_id)
            if chats:
                for sess_id, title_text, _ in chats:
                    display = title_text[:30].strip() + "..." if title_text and len(title_text) > 30 else (title_text or "Chat")
                    if st.button(f"{display}", key=f"chat_{sess_id}", use_container_width=True):
                        st.session_state.session_id = str(sess_id)
                        st.session_state.messages = load_specific_session(user_id, sess_id)
                        st.session_state.chat_title = display
                        st.query_params["session_id"] = str(sess_id)
                        st.rerun()
            else:
                st.caption("No chat history yet")
        except psycopg2.Error as db_err:
            logging.getLogger(__name__).error(f"Database error loading sidebar: {db_err}")
            st.caption("Database error loading history")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Sidebar history load failed: {e}")
            st.caption("Unable to load history")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Divider above Theme/Logout
        st.markdown("---")
        
        # Fixed bottom section
        st.markdown('<div class="sidebar-fixed-bottom">', unsafe_allow_html=True)
        
        # Logout button
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            st.session_state.clear()
            st.session_state.page = "auth_choice"
            st.query_params.clear()
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    # --- PROFILE BUTTON in SIDEBAR ---
    user_initial = user_name[0].upper() if user_name else "G"
    with st.sidebar:
        st.markdown("---")

    # --- TOP HEADER with Profile button at top left ---
    # COMMENTED OUT: Profile icon and button
    # col_profile, col_title = st.columns([1, 8])
    # with col_profile:
    #     if st.button(f"👤 {user_initial}", key="profile_btn_top", help="Profile & Emergency Contacts"):
    #         st.session_state.page = "profile"
    #         st.rerun()
    col_title = st.columns(1)[0]
    with col_title:
        st.markdown(f"""
            <div style="text-align: center; padding: 10px 0;">
                <div style="font-size: 18px; font-weight: bold; color: #fff;">{safe_html(st.session_state.chat_title)}</div>
            </div>
        """, unsafe_allow_html=True)

    # --- CHAT MESSAGES ---
    
    # New sessions should start empty and wait for the user's first message.
    
    # Display messages
    st.markdown('<div class="chat-messages">', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        msg_time = msg.get("time", "")
        time_html = f'<div style="font-size:0.7rem;color:rgba(255,255,255,0.35);margin-top:4px;">{safe_html(msg_time)}</div>' if msg_time else ""
        is_flag = msg.get("is_flag", False)

        if msg["role"] == "user":
            st.markdown(f"""
                <div class="user-msg-wrap">
                    <div class="user-msg">{safe_html(msg["content"])}{time_html}</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            # Check if this is a flag message (high/extreme risk alert)
            if is_flag:
                st.markdown(f"""
                    <div class="bot-msg-wrap">
                        <div class="bot-msg flag-msg" style="background: linear-gradient(135deg, rgba(255, 67, 54, 0.3), rgba(229, 57, 53, 0.3)); border-left: 4px solid #ff4336; border-radius: 8px; padding: 12px 16px; margin: 8px 0;">
                            {msg["content"]}{time_html}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div class="bot-msg-wrap">
                        <div class="bot-msg">{safe_html(msg["content"])}{time_html}</div>
                    </div>
                """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Spacer for fixed input
    st.markdown("<div style='height: 120px;'></div>", unsafe_allow_html=True)

    # --- QUICK REPLY BUTTONS (Start Only) ---
    # Show quick replies ONLY if chat is empty (start of conversation)
    if not st.session_state.messages:
        st.markdown("""
        <style>
        .quick-replies {
            position: fixed;
            bottom: 75px;
            left: 320px;
            right: 20px;
            max-width: 800px;
            margin: 0 auto;
            z-index: 999;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .quick-replies button {
            background: rgba(82, 113, 255, 0.15) !important;
            border: 1px solid rgba(82, 113, 255, 0.4) !important;
            border-radius: 20px !important;
            color: #B0C4FF !important;
            padding: 6px 16px !important;
            font-size: 0.85rem !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
        }
        .quick-replies button:hover {
            background: rgba(82, 113, 255, 0.3) !important;
            border-color: rgba(82, 113, 255, 0.7) !important;
            color: #FFFFFF !important;
        }
        /* P3 #29: Mobile-responsive quick replies */
        @media (max-width: 768px) {
            .quick-replies {
                left: 10px;
                right: 10px;
                bottom: 70px;
                gap: 6px;
            }
            .quick-replies button {
                font-size: 0.75rem !important;
                padding: 5px 10px !important;
            }
        }
        /* P3 #26: Typing indicator animation */
        .typing-dots {
            display: inline-flex;
            gap: 4px;
            padding: 6px 0;
        }
        .typing-dots span {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: rgba(255,255,255,0.5);
            animation: typing-bounce 1.4s infinite ease-in-out;
        }
        .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
        .typing-dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing-bounce {
            0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
            40% { opacity: 1; transform: scale(1.1); }
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Opening greeting — ice-breaker options
        quick_options = [
            ("How's my day? Let me share", "qr_share_day"),
            ("I'm feeling stressed", "qr_stressed"),
            ("I just want to chat", "qr_casual"),
            ("I need some advice", "qr_advice"),
        ]
        
        if quick_options:
            qr_cols = st.columns(len(quick_options))
            for i, (label, key) in enumerate(quick_options):
                with qr_cols[i]:
                    if st.button(label, key=key, use_container_width=True):
                        st.session_state.quick_reply_msg = label
                        st.rerun()

    # --- CHAT INPUT - Uses st.chat_input which handles Enter key and clears after send ---
    # Check if a quick reply was clicked
    quick_msg = st.session_state.pop("quick_reply_msg", None)
    prompt = quick_msg or st.chat_input("Type a message...", key="chat_input")
    
    # Process message - INSTANT user message display
    if prompt and prompt.strip():
        _roll_session_if_idle(user_id, idle_minutes=SESSION_IDLE_MINUTES)
        start_time = time.time()
        user_time = datetime.now()
        
        # Add user message immediately to session with timestamp (#27)
        st.session_state.messages.append({"role": "user", "content": prompt, "time": datetime.now().strftime("%I:%M %p")})
        
        # Update chat title from first user message
        if len([m for m in st.session_state.messages if m["role"] == "user"]) == 1:
            st.session_state.chat_title = prompt[:30] + "..." if len(prompt) > 30 else prompt
        
        with st.spinner("Thinking..."):
            try:
                neg_words = [
                    "stress", "stressed", "anxious", "worried", "sad",
                    "sleep", "panic", "tired", "exhausted",
                ]
                has_neg = [w for w in neg_words if w in prompt.lower()] or None

                # P1 #22: Retry any pending saves from prior failures
                pending = []
                while not _pending_save_queue.empty():
                    try:
                        pending.append(_pending_save_queue.get_nowait())
                    except Exception:
                        break
                for ps in pending:
                    try:
                        pending_ts = ps.get("ts", datetime.now())
                        if isinstance(pending_ts, str):
                            try:
                                pending_ts = datetime.fromisoformat(pending_ts)
                            except Exception:
                                pending_ts = datetime.now()

                        pending_analysis = ps.get("analysis", {}) or {}

                        pending_saved = save_chat_message(
                            user_id,
                            ps["session_id"],
                            ps["user_message"],
                            ps.get("assistant_response", ""),
                            pending_ts,
                            datetime.now(),
                            latency=0.0,

                            risk_level=pending_analysis.get("risk_level", "low"),
                            safety_action=pending_analysis.get("safety_action", "normal"),
                            intent_label=pending_analysis.get("intent_label", "general_chat"),
                            response_mode=pending_analysis.get("response_mode", "normal_chat"),
                            memory_used=pending_analysis.get("memory_used", False),
                            memory_type=pending_analysis.get("memory_type", ""),
                            escalation_flag=pending_analysis.get("escalation_flag", False),
                            final_reply_agent=pending_analysis.get("final_reply_agent", "coach"),
                            fallback_triggered=pending_analysis.get("fallback_triggered", False),
                            rag_used=False,  # Pending retries don't have fresh RAG data
                            rag_source="-",
                            retrieved_count=None,
                            retrieval_score=None,
                            grounded_flag=False,
                            rag_benefit_flag=False,
                        )
                        if not pending_saved:
                            raise RuntimeError("save_chat_message returned False during pending retry")
                        _schedule_session_finalization(
                            user_id,
                            ps["session_id"],
                            idle_minutes=SESSION_IDLE_MINUTES,
                        )
                    except Exception as pending_err:
                        logger.warning("Retry of pending save failed, discarding: %s", pending_err)

                # P1 #3: Single pipeline call (no redundant retry)

                # History-aware query enrichment — instead of passing only the raw
                # current message as the RAG query, prepend the last 2 conversation
                # turns so RAG understands context like "what should I do about it?"
                # without knowing "it" refers to panic attacks from the previous turn.
                _rag_query = prompt
                _past_turns = st.session_state.get("messages", [])[-4:]  # last 2 pairs
                if _past_turns:
                    _history_lines = []
                    for _msg in _past_turns:
                        _role = "User" if _msg.get("role") == "user" else "Assistant"
                        _text = str(_msg.get("content", "")).strip()
                        if _text:
                            _history_lines.append(f"{_role}: {_text[:200]}")
                    if _history_lines:
                        _rag_query = "\n".join(_history_lines) + f"\nUser: {prompt}"

                # harsh changes start
                # harsh changes end

                # CRITICAL: Early crisis detection (catches imminent danger messages)
                is_extreme_crisis, crisis_risk_level, flagged_crisis_keywords = _detect_extreme_crisis(prompt)
                crisis_detected_early = crisis_risk_level in ("high", "medium")

                if crisis_detected_early:
                    pass

                # Intent-based memory fetching: only fetch what's needed (exact engine.py logic)
                has_session_context = bool(st.session_state.get("messages", []))
                detected_intent, required_memory = _detect_intent_from_prompt(prompt, has_session_context=has_session_context)

                # Override intent to crisis if any high/extreme risk detected
                # CRITICAL: In HIGH or EXTREME risk/crisis situations, focus on immediate safety
                # - current_session: understand what they just said RIGHT NOW
                # - previous_sessions: understand how they got through crises BEFORE
                # - long_term_memory: understand what coping strategies WORKED for them
                if crisis_risk_level in ("high", "extreme") or is_extreme_crisis:
                    detected_intent = "crisis"
                    required_memory = ["current_session", "previous_sessions", "long_term_memory"]
                    risk_label = "🚨 EXTREME CRISIS" if is_extreme_crisis else "⚠️ HIGH RISK CRISIS"
                needs_rag_for_intent = _get_rag_needed_for_intent(detected_intent)
                # Convert memory_types list to string for database storage
                memory_type_str = ", ".join(required_memory) if required_memory else ""

                if required_memory:                    # Use selective fetching - only get what's needed for this intent
                    mem = fetch_selective_context(
                        user_id,
                        st.session_state.session_id,
                        memory_types=required_memory,
                        neg_words=has_neg,
                        query_text=_rag_query,
                    )
                else:
                    mem = {}

                # harsh changes start
                rag_used = mem.get("rag_context") or []
                rag_metadata_for_db = []  # NEW: Track RAG chunks for database

                # Get RAG metadata (doc_id, source, chunk text) for storing in database
                # Only retrieve RAG if: (1) intent requires it AND (2) query has content
                if needs_rag_for_intent and _rag_query and _should_use_rag(_rag_query):
                    try:
                        from rag import retrieve_relevant_chunks_with_metadata
                        # Fetch all available chunks
                        top_k = _get_rag_top_k(detected_intent, prompt)
                        _, rag_metadata_all = retrieve_relevant_chunks_with_metadata(user_id, _rag_query, top_k=top_k)

                        # FILTER BY SIMILARITY: Keep chunks where meaning matches user query (>= 0.65 similarity)
                        # Result count depends ONLY on relevance, not on intent or message length
                        # If 1 chunk is 0.80 similar → use 1
                        # If 15 chunks are 0.65+ similar → use all 15
                        # Accuracy > chunk count
                        similarity_threshold = 0.65
                        rag_metadata_for_db = _filter_chunks_by_relevance(rag_metadata_all, similarity_threshold)

                        if rag_metadata_for_db:
                            actual_count = len(rag_metadata_for_db)
                        else:
                            rag_metadata_for_db = []
                    except Exception as e:
                        rag_metadata_for_db = []
                else:
                    pass
                # harsh changes end

                logger.info(
                    "Calling run_care_pipeline: session=%s | prompt=%s",
                    st.session_state.session_id,
                    prompt[:80],
                )

                response_text, _, analysis = st.session_state.engine.run_care_pipeline(
                    prompt, mem, user_name=user_name
                )

                # harsh changes start

                # SAVE NEW FACTS in background thread (non-blocking)
                new_facts = analysis.get("new_facts", {})
                if new_facts:
                    def _save_facts_bg(uid, sid, risk, safety, tone, facts, summary, reply_src):
                        try:
                            from database import update_master_analysis
                            update_master_analysis(
                                user_id=uid,
                                session_id=sid,
                                risk=risk,
                                safety=safety,
                                tone=tone,
                                facts=facts,
                                summary=summary,
                                reply_source=reply_src,
                            )
                        except Exception as e:
                            pass

                    threading.Thread(
                        target=_save_facts_bg,
                        args=(
                            user_id,
                            st.session_state.session_id,
                            analysis.get("risk_level", "low"),
                            analysis.get("safety_action", "normal"),
                            analysis.get("tone", "neutral"),
                            new_facts,
                            analysis.get("new_summary", ""),
                            analysis.get("final_reply_agent", "coach"),
                        ),
                        daemon=True,
                    ).start()

                # === SMART MEMORY TYPE BUILDER ===
                # Only include memory types that were ACTUALLY NEEDED and USED
                memory_types_final = set()
                response_lower = (response_text or "").lower()
                agent_memory_output = (analysis.get("agent_memory_output") or analysis.get("agent_memory") or "").strip()

                # 1. **CURRENT_SESSION**: Include for followup questions and active conversation
                # ALWAYS include unless it's just a casual greeting
                if detected_intent != "casual_greeting":
                    memory_types_final.add("current_session")
                # 2. **LONG_TERM_MEMORY**: Only if response references past patterns or recurring issues
                # Check TWO conditions:
                # (a) Response mentions pattern indicators, OR
                # (b) Intent is coping/emotional_support AND we have prior memory to reference
                pattern_indicators = ["like you", "as you've", "you tend to", "you often", "in the past",
                                    "you usually", "pattern", "recurring", "again", "before", "previously",
                                    "similar to", "same as", "used to", "always", "never"]
                uses_long_term = any(phrase in response_lower for phrase in pattern_indicators)
                has_prior_context = agent_memory_output and agent_memory_output.lower() != "no"

                if uses_long_term:
                    memory_types_final.add("long_term_memory")
                elif (detected_intent in ["coping_request", "emotional_support"]) and has_prior_context:
                    memory_types_final.add("long_term_memory")
                # 3. **PREVIOUS_SESSIONS**: Only when continuing from a specific past session
                #    Include session NAME/context for clarity
                if detected_intent == "continuity_followup":
                    session_context = st.session_state.get("chat_title", "Earlier Session")
                    # Format: "previous_sessions(SessionName)" to show which session user is referencing
                    previous_sessions_label = f"previous_sessions({session_context})"
                    memory_types_final.add(previous_sessions_label)
                # 4. **ONBOARDING_PROFILE**: NEVER include automatically
                # Reason: Greetings don't need it (uses user_name from session),
                # and it's wasted database fetch. Only include if explicitly needed for analysis.
                # NOT USED: Don't automatically fetch onboarding_profile
                # if assistant_msg_count == 0:
                #     memory_types_final.add("onboarding_profile")

                # 5. **RAG_DOCUMENTS**: Only when RAG retrieval actually happened
                if rag_used and rag_metadata_for_db:
                    memory_types_final.add("rag_documents")
                # CRITICAL: Use required_memory (what we FETCHED) not memory_types_final (what appeared in response)
                # memory_type_str is already set correctly from required_memory at line 2328
                # DO NOT overwrite it with memory_types_final analysis
                # memory_type_str = ", ".join(sorted(memory_types_final)) if memory_types_final else ""

                # Override risk_level, safety_action, intent_label, response_mode if crisis was detected early
                if crisis_detected_early:
                    analysis["risk_level"] = crisis_risk_level  # high or medium
                    analysis["safety_action"] = "immediate" if is_extreme_crisis else "supportive"
                    analysis["intent_label"] = "crisis"  # Must be crisis for high risk + immediate action
                    analysis["response_mode"] = "crisis_support"  # Must be crisis_support
                # CRITICAL: If engine analysis returned high risk but early detection didn't trigger,
                # update memory_type_str to include crisis context
                if analysis.get("risk_level") == "high" and not crisis_detected_early:
                    memory_type_str = "current_session, previous_sessions, long_term_memory"

                logger.info(
                    "run_care_pipeline succeeded: session=%s | reply_len=%d",
                    st.session_state.session_id,
                    len(response_text or ""),
                )

                bot_time = datetime.now()
                latency = round(time.time() - start_time, 2)

                # Prevent duplicate responses - check if last message is identical
                last_msg = st.session_state.messages[-1] if st.session_state.messages else None
                is_duplicate = (
                    last_msg and
                    last_msg.get("role") == "assistant" and
                    last_msg.get("content") == response_text
                )

                # Add alert message to response if risk is HIGH or EXTREME
                risk_level = analysis.get("risk_level", "low").lower()
                final_response = response_text
                if risk_level in ("high", "extreme"):
                    # Track high-risk turns for trusted adult field requirement
                    if "high_risk_turn_count" not in st.session_state:
                        st.session_state.high_risk_turn_count = 0
                    st.session_state.high_risk_turn_count += 1

                    # For HIGH/EXTREME risk: check for harmful validation language and interrupt
                    harmful_phrases = {
                        "kudos to you for being open about your decision",
                        "whatever you decide will be okay",
                        "whatever you decide tonight will be okay",
                        "i wish you all the best",
                        "take care during this process",
                        "goodbye",
                    }
                    response_lower = response_text.lower()
                    is_validating_suicide = any(phrase in response_lower for phrase in harmful_phrases)

                    if is_validating_suicide or risk_level == "extreme":
                        # INTERRUPT: Replace entire response with crisis protocol
                        trusted_adult_name = st.session_state.get("onboarding_profile", {}).get("trusted_adult_name", "").strip()
                        if trusted_adult_name:
                            final_response = f"Please reach out to **{trusted_adult_name}** RIGHT NOW and tell them you need immediate support. They care about you and can help."
                        else:
                            final_response = "Please contact a family member or close friend RIGHT NOW and tell them you're having thoughts of harming yourself and need immediate help. You don't have to face this alone."
                        logger.critical(f"SAFETY INTERRUPT: Suicidal ideation detected. Redirecting to trusted adult contact.")
                    else:
                        # For HIGH risk: append safety concern message
                        safety_message = "\n\n🚨 **IMPORTANT**: I am really concerned about your safety right now. Please call or go to a parent, guardian, or another trusted adult near you right away and tell them you need support now."
                        final_response = response_text + safety_message

                    logger.warning(f"HIGH/EXTREME risk detected - turn #{st.session_state.high_risk_turn_count}. Risk level: {risk_level}")

                if not is_duplicate:
                    st.session_state.messages.append({"role": "assistant", "content": final_response, "time": datetime.now().strftime("%I:%M %p")})

                    # If 3+ high-risk turns, suggest adding trusted adult info
                    if st.session_state.high_risk_turn_count >= 3:
                        trusted_adult_name = st.session_state.onboarding_profile.get("trusted_adult_name", "")
                        trusted_adult_phone = st.session_state.onboarding_profile.get("trusted_adult_phone", "")

                        if not trusted_adult_name or not trusted_adult_phone:
                            st.warning("💡 **Important**: To help us support you better, please add your trusted adult's contact info in your Profile. This helps us know who to reach out to in case of emergency.")
                            logger.info(f"Suggested trusted adult fields after {st.session_state.high_risk_turn_count} high-risk turns")
                else:
                    logger.warning("Prevented duplicate assistant response from being added")

                # Prefer AI-generated session title over raw first message (#16)
                refined_title = analysis.get("session_title") or analysis.get("new_summary")
                if refined_title and len(str(refined_title).strip()) > 3:
                    st.session_state.chat_title = str(refined_title).strip()[:40]

                def _save_bg(uid, sid, p, rt, ut, bt, lat, a, rag_meta=None, mem_type_str=""):
                    try:
                        logger.info(
                            "Background save START: session=%s | msg_len=%d | latency=%.2fs | risk=%s",
                            sid, len(p), lat, a.get("risk", "unknown")
                        )
                        logger.info(
                            "Analysis payload keys before DB save: %s",
                            sorted(list(a.keys())) if isinstance(a, dict) else "not-a-dict"
                        )
                        
                        rag_used = bool(rag_meta and len(rag_meta) > 0)
                        doc_id = [meta.get("doc_id") for meta in rag_meta] if rag_meta else None

                        # RAG tracking fields for minimal proof setup
                        rag_source = "-"  # Default to "-" for blank text fields
                        retrieved_count = None  # int field — keep None
                        retrieval_score = None  # float field — keep None
                        if rag_meta:
                            # Extract all sources from metadata items
                            sources = [meta.get("source") for meta in rag_meta if meta.get("source")]
                            rag_source = ", ".join(sources) if sources else "-"
                            retrieved_count = len(rag_meta)
                            # Calculate retrieval_score as average of chunk similarity scores
                            scores = [meta.get("similarity_score", 0) for meta in rag_meta if meta.get("similarity_score") is not None]
                            if scores:
                                retrieval_score = round(sum(scores) / len(scores), 3)
                            else:
                                retrieval_score = None

                        # ADVANCED: Intelligent grounding detection based on response analysis
                        grounded_flag = False
                        rag_benefit_flag = False
                        grounding_score = 0.0

                        if rag_used and retrieval_score and retrieval_score >= 0.65:
                            # Check if response actually references retrieved chunks
                            is_grounded, grounding_score = check_response_grounded(rt, rag_meta)
                            grounded_flag = is_grounded and retrieval_score >= 0.65

                            # RAG benefit: grounded response + high quality chunks + response improved length
                            rag_benefit_flag = (
                                grounded_flag and
                                retrieval_score >= 0.70 and
                                len(rt) > 100  # Response has sufficient detail
                            )
                            logger.debug(
                                f"RAG flags: rag_used={rag_used}, retrieval_score={retrieval_score:.3f}, "
                                f"grounded={grounded_flag} (score={grounding_score:.2f}), benefit={rag_benefit_flag}"
                            )

                        saved_ok = save_chat_message(
                            uid, sid, p, rt, ut, bt,
                            latency=lat,

                            risk_level=a.get("risk_level", "low"),
                            safety_action=a.get("safety_action", "normal"),
                            intent_label=a.get("intent_label", "general_chat"),
                            response_mode=a.get("response_mode", "normal_chat"),
                            memory_used=bool(mem_type_str),  # True if memory types were used
                            memory_type=mem_type_str if mem_type_str else "-",  # "-" for blank
                            escalation_flag=a.get("escalation_flag", False),
                            final_reply_agent=a.get("final_reply_agent", "coach"),
                            fallback_triggered=a.get("fallback_triggered", False),
                            rag_used=rag_used,
                            doc_id=doc_id,
                            rag_source=rag_source,
                            retrieved_count=retrieved_count,
                            retrieval_score=retrieval_score,
                            grounded_flag=grounded_flag,
                            rag_benefit_flag=rag_benefit_flag,
                        )
                        if not saved_ok:
                            raise RuntimeError("save_chat_message returned False")
                        ###### changes sb begin ######
                        # -------- NEW: MEMORY STORAGE --------
                        try:
                            from database import store_user_memory

                            facts = a.get("new_facts") or {}
                            meaningful_boolean_keys = {
                                "mindfulness_practice",
                                "recent_life_changes",
                                "has_support_system",
                                "support_system_available",
                                "recently_qatar_opened_its_airspace",
                                "stressed_today",
                            }

                            if isinstance(facts, dict):
                                # Handle legacy shape: {"key": "...", "value": ...}
                                if "key" in facts and "value" in facts and len(facts) == 2:
                                    fact_key = str(facts.get("key", "")).strip()
                                    fact_value = facts.get("value")
                                    fact_value_text = str(fact_value).strip()

                                    if fact_key and fact_value is not None and len(fact_value_text) > 0:
                                        if fact_value_text.lower() in {"true", "false"} and fact_key not in meaningful_boolean_keys:
                                            pass
                                        else:
                                            store_user_memory(
                                                user_id=uid,
                                                memory_type="long_term_memory",
                                                memory_key=fact_key,
                                                memory_value=fact_value_text,
                                                confidence=0.9
                                            )
                                else:
                                    for key, value in facts.items():
                                        key_text = str(key).strip()
                                        value_text = str(value).strip()

                                        if key_text in {"topic_state", "key", "value"}:
                                            continue
                                        if value_text.lower() in {"true", "false"} and key_text not in meaningful_boolean_keys:
                                            continue
                                        if value and len(value_text) > 2:
                                            store_user_memory(
                                                user_id=uid,
                                                memory_type="long_term_memory",
                                                memory_key=key_text,
                                                memory_value=value_text,
                                                confidence=0.9
                                            )
                        except Exception as mem_err:
                            logger.warning("Memory storage skipped: %s", mem_err)
                        ###### changes sb end ######

                        _schedule_session_finalization(uid, sid, idle_minutes=SESSION_IDLE_MINUTES)
                        logger.info("Background save SUCCESS: session=%s", sid)
                        _load_sidebar_chats.clear()
                    except Exception as bg_err:
                        logger.error(traceback.format_exc())
                        logger.error("Background save FAILED: session=%s | error=%s", sid, bg_err, exc_info=True)
                        # P1 #22: Queue failed save for retry
                        try:
                            _pending_save_queue.put_nowait(
                                {
                                    "session_id": sid,
                                    "user_message": p,
                                    "assistant_response": rt,
                                    "ts": ut.isoformat(),
                                    "analysis": a,
                                }
                            )
                            logger.info("Failed save queued for retry: session=%s | queue_size=%d", sid, _pending_save_queue.qsize())
                        except Exception:
                            pass

                threading.Thread(
                    target=_save_bg,
                    args=(user_id, st.session_state.session_id, prompt, final_response, user_time, bot_time, latency, analysis, rag_metadata_for_db, memory_type_str),
                    daemon=True,
                ).start()

            except (psycopg2.OperationalError, psycopg2.InterfaceError) as db_err:
                logging.getLogger(__name__).error(f"Database error in chat pipeline: {db_err}")
                fallback_text = _fallback_message(user_name)
                try:
                    _pending_save_queue.put_nowait(
                        {
                            "session_id": st.session_state.session_id,
                            "user_message": prompt,
                            "assistant_response": fallback_text,
                            "ts": user_time.isoformat(),
                        }
                    )
                except Exception:
                    pass
                # Prevent duplicate fallback
                last_msg = st.session_state.messages[-1] if st.session_state.messages else None
                if not (last_msg and last_msg.get("role") == "assistant" and last_msg.get("content") == fallback_text):
                    st.session_state.messages.append({"role": "assistant", "content": fallback_text})
            except Exception as e:
                logging.getLogger(__name__).error(f"Chat pipeline error: {e}")
                logging.getLogger(__name__).error(traceback.format_exc())

                fallback_text = _fallback_message(user_name)
                # Prevent duplicate fallback
                last_msg = st.session_state.messages[-1] if st.session_state.messages else None
                if not (last_msg and last_msg.get("role") == "assistant" and last_msg.get("content") == fallback_text):
                    st.session_state.messages.append({"role": "assistant", "content": fallback_text})

                try:
                    _pending_save_queue.put_nowait(
                        {
                            "session_id": st.session_state.session_id,
                            "user_message": prompt,
                            "assistant_response": fallback_text,
                            "ts": user_time.isoformat(),
                            "analysis": {
                                "risk_level": "low",
                                "safety_action": "normal",
                                "intent_label": "general_chat",
                                "response_mode": "normal_chat",
                                "memory_used": False,
                                "memory_type": "",
                                "escalation_flag": False,
                                "final_reply_agent": "fallback",
                                "fallback_triggered": True,
                            },
                        }
                    )
                except Exception:
                    pass

        st.rerun()


# COMMENTED OUT: Entire profile page function
# def show_profile_page(user_id, user_name):
#     """Display user profile with emergency contact management."""
#     st.set_page_config(page_title="Profile - MindWell", layout="centered")
#
#     # Initialize onboarding_profile if not exists
#     if "onboarding_profile" not in st.session_state:
#         st.session_state.onboarding_profile = {}
#
#     # Load user profile from database (always fetch fresh data)
#     from database import fetch_user_profile
#     user_data = fetch_user_profile(user_id)
#     if user_data:
#         st.session_state.onboarding_profile.update(user_data)
##     else:
##
#     # Profile header
#     col1, col2 = st.columns([4, 1])
#     with col1:
#         st.title(f"{user_name}'s Profile")
#     with col2:
#         if st.button("Back", key="back_to_chat"):
#             st.session_state.page = "chatbot"
#             st.rerun()
#
#     st.divider()
#
#     # DEBUG: Show what data is loaded
#     with st.expander("Debug: Loaded Profile Data"):
#         st.write("Session state onboarding_profile:")
#         st.json(st.session_state.onboarding_profile)
#
#     # Initialize edit mode toggle
#     if "profile_edit_mode" not in st.session_state:
#         st.session_state.profile_edit_mode = False
#
#     # Personal Information Section
#     st.subheader("Personal Information")
#
#     # Edit Profile button
#     col_edit, col_space = st.columns([1, 4])
#     with col_edit:
#         if st.button("Edit Profile" if not st.session_state.profile_edit_mode else "Cancel", use_container_width=True):
#             st.session_state.profile_edit_mode = not st.session_state.profile_edit_mode
#             st.rerun()
#
#     if not st.session_state.profile_edit_mode:
#         # VIEW MODE - Read-only display
#         col1, col2 = st.columns(2)
#         with col1:
#             st.write("**Full Name**")
#             st.write(st.session_state.onboarding_profile.get("full_name", "Not provided"))
#             st.write("**Username**")
#             st.write(st.session_state.onboarding_profile.get("username", "Not provided"))
#             st.write("**Date of Birth**")
#             dob_val = st.session_state.onboarding_profile.get("dob")
#             st.write(str(dob_val) if dob_val else "Not provided")
#         with col2:
#             st.write("**Phone Number**")
#             st.write(st.session_state.onboarding_profile.get("mobile_number", "Not provided"))
#             st.write("**Email Address**")
#             st.write(st.session_state.onboarding_profile.get("email", "Not provided"))
#     else:
#         # EDIT MODE - Editable form
#         with st.form("profile_info_form"):
#             col1, col2 = st.columns(2)
#
#             with col1:
#                 full_name = st.text_input(
#                     "Full Name *",
#                     value=st.session_state.onboarding_profile.get("full_name", ""),
#                     placeholder="e.g., John Doe"
#                 )
#                 username = st.text_input(
#                     "Username",
#                     value=st.session_state.onboarding_profile.get("username", ""),
#                     placeholder="e.g., john_doe",
#                     disabled=True
#                 )
#                 # Parse DOB from database (it's a date object or string)
#                 dob_value = st.session_state.onboarding_profile.get("dob")
#                 dob_parsed = None
#                 if dob_value:
#                     try:
#                         if isinstance(dob_value, str):
#                             from datetime import datetime
#                             dob_parsed = datetime.strptime(dob_value.split()[0], "%Y-%m-%d").date()
#                         else:
#                             dob_parsed = dob_value
#                     except:
#                         dob_parsed = None
#
#                 dob = st.date_input(
#                     "Date of Birth",
#                     value=dob_parsed,
#                     format="DD/MM/YYYY"
#                 )
#
#             with col2:
#                 phone = st.text_input(
#                     "Phone Number",
#                     value=st.session_state.onboarding_profile.get("mobile_number", ""),
#                     placeholder="+91 XXXXX XXXXX"
#                 )
#                 email = st.text_input(
#                     "Email Address",
#                     value=st.session_state.onboarding_profile.get("email", ""),
#                     placeholder="e.g., john@example.com"
#                 )
#
#             submitted = st.form_submit_button("Save Profile Information", use_container_width=True)
#
#             if submitted:
#                 if not full_name:
#                     st.error("Full Name is required")
#                 else:
#                     # Update database
#                     from database import update_user_profile
#                     update_data = {
#                         "full_name": full_name,
#                         "dob": dob,
#                         "mobile_number": phone,
#                         "email": email,
#                     }
#                     success = update_user_profile(user_id, **update_data)
#                     if success:
#                         # Update session state
#                         st.session_state.onboarding_profile.update(update_data)
#                         st.session_state.profile_edit_mode = False
#                         st.success("Profile information saved to database!")
#                         st.rerun()
#                     else:
#                         st.error("Failed to save. Please try again.")
#
#     st.divider()
#
#     # Trusted Adult Section
#     st.subheader("Trusted Adult")
#     st.write("A trusted adult who will be contacted during a crisis.")
#
#     # Load trusted adult info from database
#     from database import fetch_trusted_adult_info
#     trusted_adult_data = fetch_trusted_adult_info(user_id)
#
#     if not st.session_state.profile_edit_mode:
#         # VIEW MODE
#         st.write("**Trusted Adult Name**")
#         st.write(trusted_adult_data.get("trusted_adult_name", "") or "Not provided")
#         st.write("**Trusted Adult Phone**")
#         st.write(trusted_adult_data.get("trusted_adult_phone", "") or "Not provided")
#     else:
#         # EDIT MODE
#         with st.form("trusted_adult_form"):
#             trusted_name = st.text_input(
#                 "Trusted Adult Name",
#                 value=trusted_adult_data.get("trusted_adult_name", ""),
#                 placeholder="e.g., Mom, Dad, Counselor"
#             )
#             trusted_phone = st.text_input(
#                 "Trusted Adult Phone",
#                 value=trusted_adult_data.get("trusted_adult_phone", ""),
#                 placeholder="+91 XXXXX XXXXX"
#             )
#             submitted = st.form_submit_button("Save Trusted Adult Info", use_container_width=True)
#
#             if submitted:
#                 from database import save_trusted_adult_info
#                 success = save_trusted_adult_info(user_id, trusted_name, trusted_phone)
#                 if success:
#                     st.success("Trusted adult information saved!")
#                 else:
#                     st.error("Failed to save. Please try again.")
#
#     st.divider()
#
#     # Emergency Contacts Section
#     st.subheader("Emergency Contacts")
#     st.write("Add close people who will be notified when your risk level is high or extreme.")
#
#     with st.form("add_contact_form"):
#         st.markdown("**Add New Contact**")
#         col1, col2 = st.columns(2)
#         with col1:
#             contact_name = st.text_input("Contact Name *", placeholder="e.g., Mom, Best Friend")
#             relationship = st.selectbox(
#                 "Relationship *",
#                 ["Parent", "Sibling", "Friend", "Spouse/Partner", "Therapist", "Other"]
#             )
#         with col2:
#             contact_phone = st.text_input("Phone Number (SMS) *", placeholder="+1 (555) 123-4567")
#             notification_enabled = st.checkbox("Enable notifications", value=True)
#
#         submitted = st.form_submit_button("Add Contact", use_container_width=True)
#
#         if submitted:
#             if not contact_name or not contact_phone:
#                 st.error("Please fill in Name and Phone Number")
#             elif len(contact_phone) < 10:
#                 st.error("Please enter a valid phone number")
#             else:
#                 # TODO: Save to database after table is created
#                 st.success(f"Contact '{contact_name}' added! They will receive SMS when risk is HIGH/EXTREME")
#                 st.balloons()
#
#     st.divider()
#
#     # Display Saved Contacts
#     st.subheader("Your Emergency Contacts")
#     st.write("These people will get notified: **'{username} needs you at this time so please reach out to him'**")
#
#     # TODO: Fetch from database and display
#     st.info("No contacts added yet. Add your first emergency contact above!")
#
#     st.divider()
#
#     st.divider()
#
#     # Account Settings - Logout only
#     if st.button("Logout", use_container_width=True):
#         st.session_state.user_id = None
#         st.session_state.page = "welcome"
#         st.rerun()
