"""
Multi-Agent Engine for MindWell application.
Contains agent prompts and the orchestration engine for mental wellness support.
"""

import json
import logging
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from llm_provider import LLMProvider

try:
    import streamlit as st
except Exception:
    st = None

logger = logging.getLogger(__name__)


# ===================== SAFETY PRE-SCREENING =====================

HIGH_RISK_TRIGGER_WORDS = {
    "suicide", "suicidal", "kill myself", "end my life", "end it all", "want to die","hurt myself",
    "wanna die", "better off dead", "no reason to live", "self-harm", "self harm"," no hope",
    "cut myself", "cutting", "hurt myself", "overdose", "jump off", "hang myself", "take pills",
    "slit", "bleed out", "dont want to live", "don't want to live","pain", "hurt myself",
    "not worth living", "nothing to live for",
}

IMPLICIT_DISTRESS_PATTERNS = [
    re.compile(r"\bi don'?t see the point\b"),
    re.compile(r"\bwhat'?s the use\b"),
    re.compile(r"\btired of everything\b"),
    re.compile(r"\bi(?:'m| am) done\b"),
    re.compile(r"\bcan'?t do this anymore\b"),
    re.compile(r"\bno point in trying\b"),
    re.compile(r"\bnobody (?:would|will) (?:miss|notice|care)\b"),
    re.compile(r"\beveryone (?:would be|is) better off without me\b"),
    re.compile(r"\bi(?:'m| am) a burden\b"),
    re.compile(r"\bworld would be better without me\b"),
]

MEDIUM_RISK_PATTERNS = [
    re.compile(r"\bi feel (?:so |very |really )?(?:worthless|hopeless|helpless|pointless|meaningless)\b"),
    re.compile(r"\bi(?:'m| am) (?:worthless|hopeless|helpless|depressed)\b"),
    re.compile(r"\bi (?:can't|cant) (?:take it|handle this|go on)\b"),
    re.compile(r"\bi(?:'m| am) (?:falling apart|giving up|breaking down)\b"),
    re.compile(r"\bi hate myself\b"),
    re.compile(r"\bno (?:one|body) cares (?:about me)?\b"),

    re.compile(r"\bi feel like (?:hitting|beating|hurting|attacking) someone\b"),
    re.compile(r"\bi want to (?:hit|beat|hurt|attack) someone\b"),
    re.compile(r"\bi might (?:hit|beat|hurt|attack) someone\b"),

    re.compile(r"\bi(?:'m| am) (?:so |very |really )?angry(?: right now)?\b"),
    re.compile(r"\bi(?:'m| am) (?:furious|enraged|out of control)\b"),
    re.compile(r"\bi feel like I could (?:hit|hurt|attack) someone\b"),
    re.compile(r"\bi don't trust myself right now\b"),
]

SAFETY_TRIGGER_WORDS = HIGH_RISK_TRIGGER_WORDS.copy()


# ===================== MEMORY / CONTINUITY HELPERS =====================

PAST_REFERENCE_PHRASES = [
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
]

PAST_REFERENCE_REGEX = [
    re.compile(r"\bremember\b.*\b(earlier|before|last time|yesterday|week)\b"),
    re.compile(r"\b(still|same)\b.*\b(problem|issue|situation|relationship|thing)\b"),
    re.compile(r"\bwhat did we (talk|discuss)\b"),
    re.compile(r"\bwe (already )?(talked|discussed)\b"),
]

MEMORY_MATCH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "has", "was", "were",
    "are", "you", "your", "about", "from", "what", "when", "where", "how",
    "still", "same", "just", "again", "did", "our", "into", "been", "over",
}

# Guardrail for a specific, observed failure mode: the user asks "do you remember/know
# X" naming a specific topic, and the model confidently confirms it even when X was
# never actually mentioned anywhere in the real context available to it. Rather than
# rely on prompt wording alone (tested directly — a local model does not reliably
# follow "don't invent things" instructions), these patterns capture the named topic
# so it can be checked in code against the real context before the model ever answers.
RECALL_PROBE_TOPIC_PATTERNS = [
    re.compile(r"\b(?:do|did|would)\s+you\s+(?:remember|know|recall)\b.{0,20}?\babout\s+(?:my\s+)?([a-z][a-z \-']{2,40}?)[\?\.!]*$", re.IGNORECASE),
    re.compile(r"\b(?:did|have)\s+i\s+(?:ever\s+)?(?:tell|mention|told)\s+you\b.{0,20}?\babout\s+(?:my\s+)?([a-z][a-z \-']{2,40}?)[\?\.!]*$", re.IGNORECASE),
    re.compile(r"\byou\s+(?:remember|know)\b.{0,20}?\babout\s+(?:my\s+)?([a-z][a-z \-']{2,40}?)[\?\.!]*$", re.IGNORECASE),
    re.compile(r"\bwhat\s+([a-z][a-z \-']{2,40}?)\s+(?:have i|i have|did i|i did)\s+(?:shared|told|mentioned)\b", re.IGNORECASE),
    # Found by evaluations/memory_guardrail_eval.py: every pattern above
    # requires the literal word "about" ("do you remember about my X"), but
    # "do you remember my X" - arguably the more natural phrasing - has no
    # "about" at all and slipped past the guardrail entirely. Requiring "my"
    # right after the verb (rather than an open-ended gap) keeps this from
    # also matching generic continuity questions like "do you remember what
    # I told you yesterday?", which aren't a named topic to check.
    re.compile(r"\b(?:do|did|would)\s+you\s+(?:remember|know|recall)\s+my\s+([a-z][a-z \-']{2,40}?)[\?\.!]*$", re.IGNORECASE),
    re.compile(r"\byou\s+(?:remember|know)\s+my\s+([a-z][a-z \-']{2,40}?)[\?\.!]*$", re.IGNORECASE),
]

_HONEST_NO_RECALL_TEMPLATES = [
    "I don't think you've told me about {topic} yet — want to fill me in?",
    "That's not something you've shared with me so far. I'd love to hear about {topic} if you want to tell me.",
    "I don't have that on my radar yet — you haven't mentioned {topic} to me before. What's going on?",
]

CONTEXT_ECHO_PREFIXES = (
    "user:",
    "assistant:",
    "current-session conversation:",
    "cross-session context:",
    "past session history:",
    "known facts about this user:",
    "latest known user context:",
    "pattern detected:",
)

CONTEXT_ECHO_PATTERNS = [
    re.compile(r"^\[[A-Za-z]{3}\s+\d{1,2}\]"),
    re.compile(r"^---\s*\[new session", re.IGNORECASE),
]

######## Changes by SB ############
ONBOARDING_FIELD_MAP = {
    "How would you describe your current role?": "role",
    "What best describes your daily routine?": "routine",
    "How has your sleep been recently?": "sleep_pattern",
    "How easy is it for you to focus on tasks?": "focus_level",
    "How supported do you currently feel in your life?": "support_system",
    "Have you experienced significant life changes recently?": "recent_life_changes",
    "How comfortable are you with asking for help?": "help_seeking_comfort",
    "What currently causes you the most stress?": "primary_stressor",
    "How often do you feel mentally exhausted?": "mental_exhaustion",
    "Do you engage in mindfulness or relaxation practices?": "mindfulness_practice",
    "What are you hoping to gain from using this app?": "wellbeing_goal",
    "When feeling low or stressed, what do you do first?": "coping_style",
}

EMOTIONAL_SUPPORT_KEYWORDS = {
    "stress", "stressed", "anxious", "anxiety", "worried", "worry", "overthinking",
    "sad", "low", "hopeless", "tired", "exhausted", "burnout", "overwhelmed",
    "lonely", "angry", "frustrated", "panic", "empty"
}

# Hoisted from inside MultiAgentEngine._route_message to module level so
# router_graph.py can reuse them too, instead of becoming a fourth
# independent copy of logic that has already drifted three times.
CONTINUITY_MARKERS = [
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
    "finish that line", "finish your last line", "do you know what we were discussing",
]

REPAIR_MARKERS = [
    "wrong", "incorrect", "not what i said", "not what you said",
    "read again", "look again", "check again", "recheck"
]

SAME_SESSION_RECALL_PATTERNS = [
    "what did i tell you",
    "what did i say",
    "did i mention",
    "do you remember what we were discussing",
    "what were we discussing",
    "this conversation",
    "in this conversation",
    "in this same conversation",
    "what was it",
    "what was that",
    "so what was",
    "tell me what",
    "you said",
    "what did you say",
    "what exactly",
    "what i told",
    "i told you",
    "i said",
    "i have told you",
    "i already told",
    # kept in sync with pages.py::_SAME_SESSION_RECALL_PATTERNS — these two lists
    # do the same job (recognizing "please recall this conversation" phrasing) and
    # had drifted apart, which is exactly what let "do you have context what we
    # were discussing?" be fetched as memory but not treated as a recall request.
    "what we have discussed",
    "what we discussed",
    "we discussed",
    "what we talked about",
    "we talked about",
    "remember discussing",
    "we were discussing",
    "about what we",
    "earlier we",
]

SHORT_FOLLOWUP_MARKERS = {
    "continue", "go on", "tell me more", "yes continue", "yes, continue",
    "yes explore", "explore", "complete it", "complete your sentence",
    "yes acknowledge", "acknowledge", "elaborate",
    "okay continue", "ok continue", "carry on",
}

COPING_KEYWORDS = {
    "help", "suggest", "advice", "cope", "coping", "manage", "what should i do",
    "how can i", "exercise", "breathe", "breathing", "routine", "habit", "focus",
    "provide", "give", "techniques", "strategies", "methods", "tips", "ways to"
}

# Smart intent distinction: event vs emotional response
EVENT_MARKERS = {
    "went to", "visited", "happened", "today i", "yesterday i", "we had",
    "i met", "i saw", "i attended", "just came from", "i finished", "i completed",
    "i started", "i joined", "i got", "i found", "i bought", "i tried",
    "i did", "we went", "we did", "there was", "he said", "she said",
    "they told", "i heard", "i read", "i watched", "got invited", "was invited"
}

EMOTION_WORDS = {
    "sad", "happy", "anxious", "scared", "depressed", "overwhelmed",
    "stressed", "angry", "frustrated", "lonely", "hurt", "worried",
    "upset", "devastated", "hopeless", "numb", "guilty", "ashamed",
    "relieved", "excited", "nervous", "afraid", "broken", "lost",
    "crying", "cried", "can't sleep", "cant sleep", "exhausted",
    "miserable", "terrible", "awful", "horrible"
}

# ===================== AGENT PROMPTS =====================

AGENT_PROMPTS = {
    "safety": """
ROLE: You are Safety Agent.
Only detect risk and output JSON. No advice, no extra text.

OUTPUT JSON:
{"risk":"low|medium|high","flagged_words":["..."],"issues":"short reason"}
""",
    "memory": """
ROLE: You are Memory Agent.
Extract insights from this turn so other agents can personalize their response.
You RECALL what is already known about this user — you do not give advice or
tell the user what to do. Advice and coaching are the Coach agent's job, not
yours; writing instructions in memory_recall blurs that separation.

Rules:
- Extract only verifiable facts from this turn; use concrete keys. Use {} if no new fact.
- session_summary: 1-2 concise sentences — topic, emotional arc, follow-up direction.
- session_title: a short title.
- memory_recall: describe what you already know about this user from past
  context — a coping strategy that worked FOR THEM before, an emotional
  pattern, or what tone helps them. This is a recall of existing history,
  phrased as a description ("they found X helpful before"), never as an
  instruction ("try X" / "notice X" / "take a deep breath"). One or two
  sentences. If nothing relevant is known yet, say so briefly instead of
  inventing advice.

OUTPUT JSON:
{
  "tone":"specific emotional tone",
  "current_topic":"short topic label",
  "topic_lock":true,
  "new_fact":{"<short_fact_name>":"<fact_value>"} (for example {"occupation":"nurse"}; use {} if there is no new fact — never use the literal words "key" or "value" as the field name),
  "memory_recall":"most useful actionable recall, concise, phrased as description not instruction",
  "session_title":"short title",
  "session_summary":"concise summary for future continuity"
}
""",
# The Orchestrator LLM agent (intent_label/response_mode/memory_needed/
# memory_types/escalation_flag classification) was removed 2026-08-27 -
# router_graph.py's LangGraph route() has produced this exact same JSON
# shape deterministically since the routing migration, and the Orchestrator
# LLM call itself had already been fully disabled (commented out, its
# result unconditionally set to "" for every message) well before this
# cleanup. See run_care_pipeline's route_decision - that's the real
# orchestrator now.
#     "coach": """
# ROLE: High-risk support helper.
# Used only for high-risk messages.
# Keep response short, direct, and grounding.
# Return only response text.
# """,

#### changes by SB start #######
"coach": """
ROLE: You are the Coach Agent.
You are ALWAYS the final responder to the user.

You will receive:
- the user message
- safety constraints
- response mode
- relevant memory context if available

Behavior:
- Be warm, grounded, and specific.
- Stay on the user's current topic.
- Be concise, focused, and natural.
- Keep the reply concise and focused.
- Default to 2-4 short sentences.
- Do not give long explanations unless the user explicitly asks for detail or analysis.
- Prefer a short complete reply over a longer detailed reply; always end cleanly, not mid-sentence.
- Ask at most one question, and only if necessary or clearly helpful.
- If the user asks for bullets, steps, or a list, give a compact list and stop.
- If the user sounds frustrated, correcting, or impatient, reduce verbosity further and avoid repeated reassurance.
- Use INTENT LABEL as the primary style and length control when it is provided.
- Mode-specific limits:
  - continuity_followup: reply in 1-2 short sentences, stay on the same topic, and do not introduce anything new.
  - continuity_followup for incomplete, correction, or repair-style prompts: complete or correct only the unfinished thought or requested line, then stop.
  - emotional_support: reply in 2-3 short supportive sentences and include at most 1 gentle practical suggestion.
  - coping_request: give 3-5 compact bullets or steps, then stop.
  - crisis: keep the reply short, direct, grounding, and safety-oriented.
- If risk is high, prioritize immediate grounding and supportive safety-oriented language.
- **CRITICAL - SUICIDAL IDEATION PROTOCOL:** If user mentions suicide, self-harm, or wanting to die:
  - IMMEDIATELY redirect to trusted adult contact (DO NOT validate or accept their plan)
  - If trusted_adult_name is provided: "Please reach out to [trusted_adult_name] RIGHT NOW and tell them you need immediate support"
  - If NOT provided: "Please contact a family member or close friend RIGHT NOW and tell them you're having suicidal thoughts and need immediate help"
  - Keep response SHORT and DIRECT - max 1-2 sentences
  - Emphasize this is NOT a goodbye, support is available NOW
  - Do NOT say things like "whatever you decide will be okay" or "goodbye"
  - Do NOT provide coping tips or memory comparisons - focus ONLY on trusted adult contact
- If memory is provided and risk is NOT extreme, use it like a close friend who remembers — reference specific things naturally, match their emotional tone from past sessions. Do NOT list facts robotically. Weave memories into your response only when they genuinely matter.
- If risk is EXTREME (suicidal ideation), DO NOT use memory - it distracts from immediate crisis intervention.
- CRITICAL: If the user asks whether you remember, know, or were told something specific (a topic, event, place, or feeling), only confirm it if that exact thing literally appears in the FRIEND CONTEXT or CURRENT SESSION RECENT TURNS given to you below. Having *some* context available does not mean every topic the user asks about is covered by it — check specifically for the thing they asked about. If it is not literally there, say plainly that they haven't mentioned that specific thing to you yet and ask them to share it. Never invent a past conversation, a fact about the user, or an emotion they supposedly shared just because they asked "do you remember" — inventing a false memory is worse than admitting you don't have it.
- Never output placeholder or template text such as "[insert ... if any]", "[specific detail]", or similar bracketed fill-in-the-blank text — if you don't have the specific detail, say so in plain words instead of leaving a placeholder.
- When the user describes a personal situation, respond to their specific concern first before giving any general background.
- When the user expresses stress, anxiety, confusion, disappointment, or asks for support,
  prioritize emotional support and practical guidance over topic analysis.
- Do not switch into broad explanation mode unless the user explicitly asks for analysis.
- If the user says they are stressed about a topic, respond to the stress first, not the topic itself.
- Do not switch into encyclopedic, broad, or generic explanation unless the user explicitly asks for that kind of overview.
- When the user asks what they said earlier, what you said earlier, or asks for recall/correction,
  answer using only CURRENT SESSION RECENT TURNS (SOURCE OF TRUTH).
- In continuity_followup mode, if the user asks about your last sentence or last reply,
  refer to the immediately previous assistant turn when it is available.
- In continuity_followup mode, if the user says the previous sentence was incomplete,
  complete or restate only the unfinished thought.
- In continuity_followup mode, do not ask a clarifying question first if the needed prior turn is available.
- In continuity_followup mode, continue the prior conversational act from the current session.
  For very short prompts like "continue", "go on", "yes acknowledge", or "tell me more",
  treat them as instructions to continue the prior intent, not as literal standalone requests.
- Do not broaden the discussion, introduce a new topic, or generalize beyond the quoted current-session turns in continuity_followup mode.
- Do not invent, infer, or fill in facts that were not explicitly stated by the user.
- If a needed detail is missing or unclear, say that briefly instead of guessing.
- Do not mention internal agents, routing, or memory systems.
- Do not output JSON.

Return only the final user-facing response text.
""",
### changes by SB end ######
}


class MultiAgentEngine:
    """Optimized 4-agent parallel engine for mental wellness."""

    def __init__(self):
        self.agents = ["safety", "memory", "coach"]
        self.message_count = 0
        self.ask_question_cooldown = 0
        self._session_buffer = []
        # Per-agent-call elapsed seconds from the most recent
        # run_care_pipeline() call, keyed by agent name. Read by
        # evaluations/latency_benchmark.py; not used elsewhere. Reset at
        # the start of each run_care_pipeline() call, not accumulated
        # across turns.
        self._agent_timings = {}
        if st is not None:
            self.message_count = int(st.session_state.get("_engine_msg_count", 0))
            self.ask_question_cooldown = int(st.session_state.get("_engine_q_cooldown", 0))
            self._session_buffer = list(st.session_state.get("_engine_session_buffer", []))

    def _persist_runtime_state(self):
        if st is None:
            return
        st.session_state["_engine_msg_count"] = int(self.message_count)
        st.session_state["_engine_q_cooldown"] = int(self.ask_question_cooldown)
        st.session_state["_engine_session_buffer"] = list(self._session_buffer[-30:])

    def _needs_safety_check(self, user_input):
        user_lower = (user_input or "").lower().strip()
        for trigger in HIGH_RISK_TRIGGER_WORDS:
            if trigger in user_lower:
                return True
        for pattern in MEDIUM_RISK_PATTERNS:
            if pattern.search(user_lower):
                return True
        for pattern in IMPLICIT_DISTRESS_PATTERNS:
            if pattern.search(user_lower):
                return True

        neg_markers = [
            "worthless", "hopeless", "helpless", "pointless", "meaningless",
            "useless", "broken", "empty", "numb", "pain", "suffering",
            "drained", "exhausted", "stuck", "alone",
        ]
        neg_count = sum(1 for w in neg_markers if w in user_lower)
        if neg_count >= 3:
            return True

        first_person = [" i ", " i'm ", " ive ", " i've ", " me ", " my "]
        subtle_distress = [
            "no point", "nothing matters", "can't cope", "cannot cope",
            "feels empty", "done with everything",
        ]
        if any(tok in f" {user_lower} " for tok in first_person) and any(p in user_lower for p in subtle_distress):
            return True
        return False

    def _references_past(self, user_input):
        user_lower = (user_input or "").lower().strip()
        for phrase in PAST_REFERENCE_PHRASES:
            if phrase in user_lower:
                return True
        for pattern in PAST_REFERENCE_REGEX:
            if pattern.search(user_lower):
                return True
        return False

    def _extract_keywords(self, text):
        tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
        return {tok for tok in tokens if len(tok) > 2 and tok not in MEMORY_MATCH_STOPWORDS}

    def _find_unverified_recall_topic(self, user_text, available_context):
        """
        Detect "do you remember/know about X" style questions naming a specific topic,
        and check whether X is actually present in the real context the Coach is about
        to receive. Returns the matched topic phrase if X is NOT grounded anywhere in
        available_context (the guardrail should fire), or None if either the message
        isn't this kind of question, or the topic genuinely is present (let the LLM
        answer normally — it has real grounds to).
        """
        text = (user_text or "").strip()
        if not text:
            return None

        topic_phrase = None
        for pattern in RECALL_PROBE_TOPIC_PATTERNS:
            match = pattern.search(text)
            if match:
                topic_phrase = match.group(1).strip()
                break
        if not topic_phrase:
            return None

        topic_keywords = self._extract_keywords(topic_phrase)
        if not topic_keywords:
            # Nothing specific enough to check (e.g., just stopwords) — let the LLM
            # handle it normally rather than risk a false-positive block.
            return None

        # available_context always ends with the current question echoed back in
        # (e.g. "User: you remember about my relocation?") so the topic word the
        # person just used would otherwise always trivially match itself. Strip the
        # current message out before searching so only genuine prior context counts.
        haystack = (available_context or "").lower()
        current_line = text.lower()
        haystack = haystack.replace(current_line, "")
        haystack_words = set(re.findall(r"[a-z0-9']+", haystack))

        for kw in topic_keywords:
            if kw in haystack:
                return None  # exact match in real prior context — fine
            # Plain substring matching misses simple word-form variants (e.g. the
            # user asks about "relocation" but the stored context says "relocated").
            # A shared 6-character prefix is a cheap, effective stand-in for real
            # stemming for this purpose.
            if len(kw) >= 6:
                stem = kw[:6]
                if any(w.startswith(stem) for w in haystack_words if len(w) >= 6):
                    return None

        return topic_phrase

    def _is_context_echo_line(self, line):
        stripped = str(line or "").strip()
        if not stripped:
            return False
        low = stripped.lower()
        if any(low.startswith(prefix) for prefix in CONTEXT_ECHO_PREFIXES):
            return True
        if "user (mood:" in low:
            return True
        for pattern in CONTEXT_ECHO_PATTERNS:
            if pattern.search(stripped):
                return True
        return False

    def _sanitize_reply_text(self, text):
        """Strip leaked context/transcript lines and dedupe repeated sentences."""
        if not text:
            return ""
        raw = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not raw:
            return ""

        cleaned_lines = []
        seen_lines = set()
        for line in raw.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if self._is_context_echo_line(stripped):
                continue
            if "current-session conversation:" in low or "cross-session context:" in low:
                continue
            if low in seen_lines:
                continue
            seen_lines.add(low)
            cleaned_lines.append(stripped)

        cleaned = " ".join(cleaned_lines).strip()
        if not cleaned:
            return ""

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        deduped = []
        seen_sentences = set()
        for sentence in sentences:
            normalized = sentence.strip()
            if not normalized:
                continue
            key = re.sub(r"\s+", " ", normalized.lower())
            if key in seen_sentences:
                continue
            seen_sentences.add(key)
            deduped.append(normalized)
        return " ".join(deduped).strip()

    def _trim_context(self, text, max_chars=6000):
        if not text or len(text) <= max_chars:
            return text
        guard = "\n...[older context trimmed]...\n"
        head = int(max_chars * 0.62)
        tail = max_chars - head - len(guard)
        if tail < 0:
            tail = 0
        return text[:head] + guard + text[-tail:]

    def _flatten_facts(self, facts, parent_key=""):
        flat = []
        if not isinstance(facts, dict):
            return flat
        for key, value in facts.items():
            joined_key = f"{parent_key}.{key}" if parent_key else str(key)
            if isinstance(value, dict):
                flat.extend(self._flatten_facts(value, joined_key))
            elif isinstance(value, list):
                flat.append((joined_key, ", ".join(str(v) for v in value[:5])))
            else:
                flat.append((joined_key, str(value)))
        return flat

    def _build_structured_summary(self, user_input, tone, topic, new_facts, memory_recall):
        """Build internal structured summary for database storage ONLY.
        This should NOT be displayed to users - it's for internal analysis."""
        sections = []
        sections.append(f"Topic: {(topic or str(user_input or '').strip()[:180])}")
        if tone:
            sections.append(f"Tone: {tone}")
        flat_facts = self._flatten_facts(new_facts)
        if flat_facts:
            sections.append("Key user details: " + "; ".join(f"{k}={v}" for k, v in flat_facts[:8]))
        # DO NOT include memory_recall in user-facing summaries
        # This is internal context only
        return " | ".join(sections)[:900]

    def _build_user_summary(self, user_input, tone, topic, new_facts):
        """Build user-friendly summary for display in greetings and UI.
        This is what users see, so it should be clear and personal."""
        sections = []
        sections.append(f"We discussed {topic}" if topic else "Our conversation")
        if tone:
            sections.append(f"(you seemed {tone})")
        return " ".join(sections)

    def _clean_summary_for_display(self, summary_text):
        """Extract clean, user-friendly text from internal structured summary.
        Removes metadata like 'Key user details:', 'Tone:', etc."""
        if not summary_text:
            return ""

        # If it's an internal structured summary, extract the topic part
        if "|" in summary_text and "Key user details:" in summary_text:
            # Extract just the topic part before metadata
            parts = summary_text.split("|")
            topic = parts[0].replace("Topic:", "").strip()
            return topic if topic else summary_text[:100]

        # Clean any internal markers that shouldn't be user-visible
        text = summary_text.replace("Referenced history:", "").strip()
        text = text.replace("Topic:", "").strip()
        text = text.replace("Tone:", "").strip()

        # Remove pipe separators if present
        text = text.replace(" | ", " ").strip()

        return text[:150]  # Cap at 150 chars for display

    def _extract_memory_message(self, memory_result):
        """
        Extract clean message from memory agent JSON response.
        Returns only the memorable/useful content (memory_recall field),
        not internal metadata (tone, current_topic, new_fact, etc).

        Args:
            memory_result: Either JSON string with memory_recall, or simple string

        Returns:
            Clean message text to display, empty string if no useful content
        """
        if not memory_result or memory_result == "No":
            return ""

        try:
            # If it's JSON string, parse it
            if isinstance(memory_result, str) and memory_result.strip().startswith("{"):
                data = json.loads(memory_result)
                # Extract the actual message field
                memory_recall = data.get("memory_recall", "")
                # Return just the memory recall message if it has content
                if memory_recall and memory_recall.strip():
                    return memory_recall.strip()
                return ""
        except (json.JSONDecodeError, ValueError):
            # If parsing fails, return as-is only if it looks like a message
            if isinstance(memory_result, str):
                text = memory_result.strip()
                # If it's not JSON-like and has actual content, return it
                if text and not text.startswith("{"):
                    return text
        return ""

    def _select_session_context(self, session_history, user_input, max_total=10):
        if not session_history:
            return []
        user_keywords = self._extract_keywords(user_input)
        scored = []
        for idx, session in enumerate(session_history):
            summary = str(session.get("summary") or "")
            tone = str(session.get("tone") or "")
            facts = session.get("facts") or {}
            facts_text = " ".join(f"{k} {v}" for k, v in self._flatten_facts(facts))
            haystack = f"{summary} {tone} {facts_text}".lower()
            overlap = sum(1 for key in user_keywords if key in haystack)
            recency_bonus = max(0, 4 - idx)
            score = overlap * 3 + recency_bonus
            scored.append((score, session))

        relevant = [sess for score, sess in sorted(scored, key=lambda s: s[0], reverse=True) if score > 2][:5]
        recent = session_history[:5]

        selected = []
        seen = set()
        for sess in relevant + recent:
            key = sess.get("session_id") or f"{sess.get('date')}|{sess.get('summary')}"
            if key in seen:
                continue
            selected.append(sess)
            seen.add(key)
            if len(selected) >= max_total:
                break
        return selected

    def _build_relevant_memory_recall(self, user_input, memory_data, min_score=3, allow_recent_fallback=False):
        if not memory_data:
            return ""
        session_history = memory_data.get("session_history") or []
        if not session_history:
            return ""

        user_keywords = self._extract_keywords(user_input)
        ranked = []
        for idx, session in enumerate(session_history):
            summary = str(session.get("summary") or "")
            tone = str(session.get("tone") or "")
            facts = session.get("facts") or {}
            facts_blob = " ".join([f"{k} {v}" for k, v in self._flatten_facts(facts)])
            haystack = f"{summary} {tone} {facts_blob}".lower()
            # Word-boundary match, not plain substring: found by
            # evaluations/memory_relevance_eval.py, "work" (from a
            # work-stress query) matched inside "...time working." in an
            # unrelated session's summary, pulling it in as a false
            # distractor purely from the substring collision - same bug
            # shape as router_graph.py::_keyword_hit and the safety
            # keyword fixes. user_keywords are always single tokens (see
            # _extract_keywords), so a plain \b...\b regex is enough here.
            overlap = sum(
                1 for key in user_keywords
                if re.search(rf"\b{re.escape(key)}\b", haystack)
            )
            recency_bonus = max(0, 3 - idx)
            score = (overlap * 3 + recency_bonus) if overlap > 0 else 0
            ranked.append((score, session))

        ranked.sort(key=lambda item: item[0], reverse=True)
        best_sessions = [session for score, session in ranked if score >= min_score][:3]
        if not best_sessions and allow_recent_fallback:
            best_sessions = session_history[:1]
        if not best_sessions:
            return ""

        lines = []
        for session in best_sessions:
            summary = (session.get("summary") or "").strip()
            if not summary:
                continue
            tone = (session.get("tone") or "neutral").strip()
            date = (session.get("date") or "recent").strip()
            lines.append(f"[{date}] {summary} (mood: {tone})")
        return " | ".join(lines)

    ########## changes by SB start #######
    def _extract_onboarding_profile(self, onboarding_rows):
        """Convert onboarding Q/A rows into a structured profile dict."""
        profile = {}
        for qa in onboarding_rows or []:
            q = str(qa.get("question") or "").strip()
            a = str(qa.get("answer") or "").strip()
            key = ONBOARDING_FIELD_MAP.get(q)
            if key and a:
                profile[key] = a
        return profile

    def _format_profile_context(self, memory_data):
        """Build onboarding-only profile text for prompts."""
        onboarding_profile = self._extract_onboarding_profile(memory_data.get("onboarding") or [])
        if not onboarding_profile:
            return ""
        profile_parts = [f"{key}: {value}" for key, value in onboarding_profile.items()]
        return "ONBOARDING PROFILE:\n" + "\n".join(f"- {item}" for item in profile_parts[:15])

    def _format_long_term_memory(self, memory_data):
        """
        Formats long-term memory from memory_data into a compact context block for the LLM.
        Covers four sources:
          1. facts         — cross-session merged facts (e.g. occupation, stress triggers)
          2. summary       — narrative summary from the most recent past session
          3. mood_history  — emotional trend across last 5 sessions
          4. user_memory   — key-value store from the user_memory table (grouped by type)
        Returns an empty string when no meaningful long-term data exists (first-time users).
        """
        parts = []

        # 1. Cross-session merged facts
        facts = memory_data.get("facts") or {}
        if isinstance(facts, dict) and facts:
            fact_lines = []
            for k, v in list(facts.items())[:20]:
                if isinstance(v, dict):
                    # nested fact group — flatten one level
                    for sub_k, sub_v in list(v.items())[:4]:
                        fact_lines.append(f"- {sub_k}: {sub_v}")
                else:
                    fact_lines.append(f"- {k}: {v}")
            if fact_lines:
                parts.append("LONG-TERM FACTS ABOUT THIS USER:\n" + "\n".join(fact_lines[:18]))

        # 2. Latest session summary (skip generic placeholders)
        summary = (memory_data.get("summary") or "").strip()
        if summary and summary not in ("First conversation.", "Continuing our conversation."):
            parts.append(f"LAST SESSION SUMMARY:\n{summary}")

        # custom changes start
        # 2b. Full past session history — show all past sessions with dates so the LLM
        # can recall conversations from days/weeks/months ago, not just the latest one.
        session_history = memory_data.get("session_history") or []
        if session_history:
            history_lines = []
            for sess in session_history[:8]:  # cap at 8 to stay within context limit
                date = (sess.get("date") or "unknown date").strip()
                sess_summary = (sess.get("summary") or "").strip()
                tone = (sess.get("tone") or "neutral").strip()
                if sess_summary and sess_summary not in (
                    "First conversation.", "General conversation", "Continuing our conversation."
                ):
                    history_lines.append(f"- [{date}] {sess_summary} (mood: {tone})")
            if history_lines:
                parts.append("ALL PAST SESSION HISTORY (most recent first):\n" + "\n".join(history_lines))
        # custom changes end

        # 3. Mood / emotional trend
        mood_history = memory_data.get("mood_history") or []
        if mood_history:
            trend = " → ".join(str(m) for m in mood_history[:5])
            parts.append(f"RECENT MOOD TREND: {trend}")

        # 4. user_memory table — grouped by memory_type, high-confidence only
        user_memory = memory_data.get("user_memory") or {}
        if isinstance(user_memory, dict):
            mem_lines = []
            for mtype, entries in user_memory.items():
                if not isinstance(entries, dict):
                    continue
                for key, value in list(entries.items())[:6]:
                    if key and value:
                        mem_lines.append(f"- [{mtype}] {key}: {value}")
            if mem_lines:
                parts.append("USER MEMORY:\n" + "\n".join(mem_lines[:12]))

        # mood_patterns is only populated when the user's message contains negative words.
        # pattern_hint gives the LLM a direct, human-readable stress pattern sentence.
        mood_patterns = memory_data.get("mood_patterns") or {}
        if isinstance(mood_patterns, dict) and mood_patterns.get("has_patterns"):
            hint = mood_patterns.get("pattern_hint", "").strip()
            topics = mood_patterns.get("recurring_topics") or []
            neg_count = mood_patterns.get("negative_count", 0)
            pattern_lines = []
            if hint:
                pattern_lines.append(hint)
            if topics:
                pattern_lines.append(f"Recurring stress topics this week: {', '.join(topics)}")
            if neg_count:
                pattern_lines.append(f"Negative signals detected in past 7 days: {neg_count}")
            if pattern_lines:
                parts.append("DETECTED MOOD PATTERN:\n" + "\n".join(f"- {l}" for l in pattern_lines))

        if not parts:
            return ""
        return "=== LONG-TERM MEMORY ===\n" + "\n\n".join(parts) + "\n=== END LONG-TERM MEMORY ==="

    def _route_message(self, user_input, references_past=False, risk_hint="low"):
        """
        Lightweight orchestrator/router before memory-heavy prompt building.
        Returns routing metadata aligned with the locked architecture.

        Delegates to router_graph.route() — the single LangGraph-based
        implementation of this decision, also used by
        pages.py::_detect_intent_from_prompt. This used to be two
        independently-maintained copies of the same logic, which drifted
        apart three times during development before the router-consistency
        test suite caught it. Deferred import: router_graph imports the
        keyword-list constants below from this module, so importing it at
        module level here would be circular.
        """
        from router_graph import route
        has_session_context = bool(self._session_buffer)
        return route(
            user_input,
            has_session_context=has_session_context,
            references_past=references_past,
            risk_hint=risk_hint,
        )
    ###### changes by SB end #######

    def _reply_has_question(self, reply):
        reply = (reply or "").strip()
        return bool(reply and "?" in reply)

    def _call_agent(self, agent_name, user_input, memory_context="", risk_level="low"):
        import time
        from langsmith import trace
        start_time = time.time()
        try:
            prompt = AGENT_PROMPTS[agent_name]
            context_size = len(memory_context) if memory_context else 0
            # Skip memory injection if risk is extreme (suicidal ideation)
            skip_memory = risk_level == "extreme"
            if agent_name in ("orchestrator", "memory", "coach") and memory_context and not skip_memory:
                prompt = prompt + (
                    f"\n\nFRIEND CONTEXT — what you genuinely know about this person:\n"
                    f"{memory_context}\n"
                    f"Use this naturally, like a close friend who remembers and cares. "
                    f"Do NOT dump facts robotically. Weave relevant memories into your response "
                    f"only when they genuinely matter for what the person just shared."
                )

            logger.info("Agent '%s' starting (context_size=%d chars)", agent_name, context_size)
            # Named per agent (safety/memory/coach) rather than a single generic
            # "_call_agent" node, so a trace actually shows which step is which —
            # the roadmap's own requirement ("use meaningful run names"). A no-op
            # (~20-50 microseconds measured) when tracing isn't configured, so
            # this never costs anything on the common path.
            # Deliberately not logging user_input or memory_context (the actual
            # conversation content) into the trace — only shapes/sizes/timing.
            # This stays true regardless of what real content ever flows through
            # here; a policy decision to trace real message content would need
            # its own explicit, reviewed change, not a side effect of this one.
            with trace(
                name=f"agent:{agent_name}",
                run_type="chain",
                inputs={"context_size_chars": context_size, "risk_level": risk_level},
                metadata={"agent_type": agent_name},
            ) as run:
                response = LLMProvider.call_llm(agent_name, prompt, user_input)
                elapsed = time.time() - start_time
                run.end(outputs={"response_len": len(response or ""), "elapsed_s": round(elapsed, 3)})

            self._agent_timings[agent_name] = round(elapsed, 3)
            preview = "empty"
            if response:
                preview = response[:100].encode("ascii", "ignore").decode("ascii")
            else:
                logger.warning("Agent '%s' returned empty response after %.2fs", agent_name, elapsed)

            logger.info("Agent '%s' completed in %.2fs: %s...", agent_name, elapsed, preview)
            return response
        except Exception as exc:
            elapsed = time.time() - start_time
            self._agent_timings[agent_name] = round(elapsed, 3)
            logger.error("Agent '%s' FAILED after %.2fs with error: %s", agent_name, elapsed, exc, exc_info=True)
            return None

    def _first_json_object_fragment(self, text):
        raw = str(text or "")
        start = raw.find("{")
        if start < 0:
            return ""

        depth = 0
        in_string = False
        escape = False

        for idx in range(start, len(raw)):
            ch = raw[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start:idx + 1]

        fragment = raw[start:]
        if depth > 0 and not in_string:
            fragment += "}" * depth
        return fragment

    def _repair_json_fragment(self, fragment):
        repaired = str(fragment or "").strip()
        if not repaired:
            return ""
        repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    def _recover_partial_json_fields(self, text):
        raw = str(text or "")
        recovered = {}

        for key in ("tone", "current_topic", "memory_recall", "session_title", "session_summary"):
            match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', raw, re.DOTALL)
            if match:
                recovered[key] = " ".join(match.group(1).strip().split())

        for key in ("topic_lock", "topic_state.locked"):
            match = re.search(rf'"{re.escape(key)}"\s*:\s*(true|false)', raw, re.IGNORECASE)
            if match:
                recovered["topic_lock"] = (match.group(1).lower() == "true")
                break

        new_fact_key = re.search(r'"new_fact"\s*:\s*\{', raw)
        if new_fact_key:
            fragment = self._first_json_object_fragment(raw[new_fact_key.start():])
            if fragment:
                try:
                    parsed = json.loads(self._repair_json_fragment(fragment))
                    if isinstance(parsed, dict):
                        recovered["new_fact"] = parsed
                except Exception:
                    pass

        return recovered

    def _extract_json(self, text):
        if not text:
            return {}

        fragment = self._first_json_object_fragment(text)
        candidates = [fragment, self._repair_json_fragment(fragment)]

        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue

        recovered = self._recover_partial_json_fields(text)
        if recovered:
            logger.info("Recovered partial JSON fields: %s", ", ".join(sorted(recovered.keys())))
            return recovered

        logger.warning("JSON parse failed for text: %s", str(text)[:120])
        return {}

    def run_care_pipeline(self, user_input, memory_data=None, user_name=None):
        import time
        pipeline_start = time.time()
        self._agent_timings = {}
        self.message_count += 1
        memory_data = memory_data or {}
        user_text = (user_input or "").strip()
        user_input_lower = user_text.lower()

        # Log pipeline initiation with memory context
        memory_summary = memory_data.get("summary", "")[:50] if memory_data.get("summary") else "none"
        facts_count = len(memory_data.get("facts", {})) if isinstance(memory_data.get("facts"), dict) else 0
        logger.info(
            "Pipeline START: user_input=%s | memory_summary=%s | facts_count=%d | has_history=%s",
            user_text[:50], memory_summary, facts_count, memory_data.get("has_history", False)
        )

        _fallback_pool = [
            "I’m here with you. What’s weighing on you most right now?",
            "I hear you. Can you tell me a little more about what’s going on?",
            "I want to understand what you’re going through. What feels hardest today?",
            "I’m listening. Take your time — what’s been on your mind?",
            "You don’t have to figure this out alone. What would help most right now?",
            "I’m with you. What’s one thing you’d like to talk through today?",
            "It sounds like something’s on your mind. I’m here — what’s happening?",
            "I want to make sure I’m supporting you well. Can you share more about how you’re feeling?",
            "I’m here and I’m not going anywhere. What’s coming up for you right now?",
            "Let’s take this one step at a time. What feels most pressing for you today?",
        ]
        fallback_text = _fallback_pool[self.message_count % len(_fallback_pool)]
        main_reply = fallback_text
        is_fallback = True

        # needs_safety = self._needs_safety_check(user_text)
        # references_past = self._references_past(user_text)
        # is_greeting = user_input_lower in {"hi", "hello", "hey", "hii", "hie", "yo", "sup", "good morning", "good evening", "good night"}
        # is_trivial = (user_input_lower in {"hi", "hello", "hey", "hii", "hie", "yo", "sup", "good morning", "good evening", "good night", "ok", "okay", "thanks", "thank you", "cool"}) and not references_past
        
        ####### changes by SB start #######
        needs_safety = self._needs_safety_check(user_text)
        references_past = self._references_past(user_text)

        is_greeting = user_input_lower in {
            "hi", "hello", "hey", "hii", "hie", "yo", "sup",
            "good morning", "good evening", "good night"
        }

        is_trivial = (
            user_input_lower in {
                "hi", "hello", "hey", "hii", "hie", "yo", "sup",
                "good morning", "good evening", "good night",
                "ok", "okay", "thanks", "thank you", "cool"
            }
        ) and not references_past

        # Lightweight orchestrator routing decision BEFORE memory-heavy use
        _routing_start = time.time()
        route_decision = self._route_message(
            user_text,
            references_past=references_past,
            risk_hint="medium" if needs_safety else "low"
        )
        self._agent_timings["_routing"] = round(time.time() - _routing_start, 3)

        ####### changes by SB end #######

        if is_greeting and not references_past:
            hour = datetime.now().hour
            greeting_prefix = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
            first_name = (user_name or "").strip().split()[0] if user_name else ""
            name_part = f" {first_name}" if first_name else ""
            greeting_text = f"{greeting_prefix}{name_part}. What's on your mind right now?"
            # if memory_data.get("has_history") and memory_data.get("summary"):
            #     # Clean the summary for user display (removes internal metadata)
            #     clean_summary = self._clean_summary_for_display(memory_data.get('summary', ''))
            #     if clean_summary:
            #         greeting_text = (
            #             f"{greeting_prefix}{name_part}. Last time we discussed {clean_summary}. "
            #             "How are things going with that today?"
            #         )
            if self.ask_question_cooldown > 0:
                self.ask_question_cooldown -= 1
            self._persist_runtime_state()
            return greeting_text, "Multi-Agent", {
                "risk": "low",
                "flagged_words": [],
                "issues": "none",
                "safety": "none",
                "tone": "friendly",
                "new_facts": {},
                "memory_recall": None,
                "new_summary": "Casual check-in",
                "session_title": "Casual check-in",
                "agent_safety": "No",
                "agent_memory": "No",
                "agent_orchestrator": "No",
                "agent_coach": "Yes",
                "agent_safety_output": "",
                "agent_memory_output": "",
                "agent_memory_raw_output": "",
                "agent_orchestrator_output": "",
                "agent_refine_output": "",
                "agent_coach_output": greeting_text,
                "is_fallback": False,
                ##### changes by SB start ##### 
                "intent_label": "casual_greeting",
                "response_mode": "casual_chat",
                "memory_needed": "false",
                "memory_types": [],
                "escalation_flag": False,
                "risk_level": "low",
                "safety_action": "normal", #new change by SB
                "memory_used": False,
                "memory_type": "",
                "final_reply_agent": "coach",
                "fallback_triggered": False,
                #### changes by SB end #####
            }

        # Run memory extraction on substantive turns so summaries/facts stay fresh.
        # needs_memory_agent = bool(memory_data) and not is_trivial
        # needs_memory_agent = bool(memory_data) and route_decision["memory_needed"] and not is_trivial #by SB
        ##### changes by SB start #######
        # needs_memory_agent = bool(memory_data) and (references_past or not is_greeting) and not is_trivial #by SB
        # deterministic_recall = self._build_relevant_memory_recall(
        #     user_text,
        #     memory_data,
        #     min_score=3 if references_past else 5,
        #     allow_recent_fallback=references_past,
        # )
        # Run memory extraction only when routing says memory is needed for this turn.
        memory_mode = str(route_decision.get("memory_needed", "false")).strip().lower()

        needs_memory_agent = (
            bool(memory_data)
            and memory_mode in ["light", "full"]
            and not is_trivial
        )

        deterministic_recall = ""
        if needs_memory_agent:
            # custom changes start
            # Lower min_score when user has history — ensures cross-session recall
            # fires even when the user doesn't explicitly say "last time" / "yesterday".
            has_history = bool(memory_data.get("has_history"))
            effective_min_score = 3 if (references_past or has_history) else 5
            allow_fallback = references_past or has_history
            deterministic_recall = self._build_relevant_memory_recall(
                user_text,
                memory_data,
                min_score=effective_min_score,
                allow_recent_fallback=allow_fallback,
            )
            # custom changes end
        #### changes by SB end #######

        # Always include the last few turns of THIS session's own buffer, regardless of
        # whether the router decided long-term/DB memory is needed. This costs nothing
        # (already in memory, no DB or LLM call) and is what was missing when the router
        # misjudged a message as not needing memory: the Coach had literally zero
        # conversation context and would confidently invent a plausible-sounding "I
        # remember..." answer rather than admit it had nothing to go on.
        source_truth_lines = []
        for u, a in self._session_buffer[-4:]:
            source_truth_lines.append(f"User: {u}")
            if a:
                source_truth_lines.append(f"Assistant: {' '.join(str(a).split())}")
        if user_text:
            source_truth_lines.append(f"User: {user_text}")
        if not source_truth_lines:
            source_truth_lines = ["(No current-session turns are available.)"]
        source_truth_block = (
            "CURRENT SESSION RECENT TURNS (SOURCE OF TRUTH):\n"
            "Trust these turns first. Use only this current-session conversation for recall and continuity. "
            "Do not rely on older summaries, previous sessions, emotional history, or inferred memory when these turns are available.\n"
            + "\n".join(source_truth_lines)
        )
        orch_context = ""
        mem_context = ""
        if memory_data and needs_memory_agent:
            common_parts = []
            profile_context = self._format_profile_context(memory_data)
            if profile_context:
                common_parts.append(profile_context)

            # Inject long-term memory (facts, last session summary, mood trend, user_memory table)
            # into common_parts so the memory agent receives it.
            long_term_ctx = self._format_long_term_memory(memory_data)
            if long_term_ctx:
                common_parts.append(long_term_ctx)

            # RAG: inject top semantically relevant chunks from rag_documents.
            # Populated by retrieve_relevant_chunks() in fetch_all_user_context.
            # Empty on first use or when nomic-embed-text is not yet pulled.
            rag_chunks = memory_data.get("rag_context") or []
            if rag_chunks:
                rag_block = (
                    "=== RETRIEVED CONTEXT (RAG) ===\n"
                    + "\n---\n".join(rag_chunks[:3])
                    + "\n=== END RETRIEVED CONTEXT ==="
                )
                common_parts.append(rag_block)

            in_session_lines = []
            for u, a in self._session_buffer[-6:]:
                in_session_lines.append(f"User: {u}")
                if a:
                    in_session_lines.append(f"Assistant: {' '.join(str(a).split())}")

            current_session_db_lines = memory_data.get("recent_messages", [])[-12:]
            combined_session_lines = []
            seen_lines = set()
            for line in current_session_db_lines + in_session_lines:
                normalized = str(line).strip().lower()
                if not normalized or normalized in seen_lines:
                    continue
                seen_lines.add(normalized)
                combined_session_lines.append(str(line))

            source_truth_lines = combined_session_lines[-12:] if combined_session_lines else [
                "(No earlier turns from the current session are available.)"
            ]

            # custom changes start
            if references_past:
                session_instruction = (
                    "The user is asking about a PREVIOUS SESSION. "
                    "Use the long-term memory, past session summaries, and facts provided below to answer. "
                    "Do NOT say you cannot recall previous conversations — use the memory data injected here."
                )
            else:
                session_instruction = (
                    "Trust these turns first. Use only this current-session conversation for recall and continuity. "
                    "Do not rely on older summaries, previous sessions, or inferred memory when these turns are available."
                )
            source_truth_block = (
                "CURRENT SESSION RECENT TURNS (SOURCE OF TRUTH):\n"
                + session_instruction + "\n"
                + "\n".join(source_truth_lines)
            )
            # custom changes end

            question_instruction = ""
            if self.ask_question_cooldown > 0:
                question_instruction = "IMPORTANT: Do NOT end with a question in this reply."

            orch_parts = [source_truth_block]
            # custom changes start
            if route_decision.get("intent_label") != "continuity_followup" or references_past:
                orch_parts += common_parts
            # custom changes end

            # deterministic_recall is scored past-session highlights relevant to the current query.
            # Previously computed above but never injected into the orchestrator prompt — wired here.
            if deterministic_recall:
                orch_parts.append(
                    "RELEVANT PAST SESSION HIGHLIGHTS (matched to current query):\n" + deterministic_recall
                )
                logger.info(f"[CONTINUITY DEBUG] Injected deterministic_recall: {deterministic_recall[:200]}")
            else:
                # Log when deterministic_recall is empty
                session_hist = memory_data.get("session_history") if memory_data else []
                logger.info(f"[CONTINUITY DEBUG] Empty deterministic_recall | references_past={references_past} | has_session_history={bool(session_hist)} | session_count={len(session_hist) if session_hist else 0}")

            orch_context = "\n\n".join(
                orch_parts
                + ([question_instruction] if question_instruction else [])
            )

            mem_recent_lines = source_truth_lines
            if not mem_recent_lines:
                mem_recent_lines = [f"User: {user_text}"]
            mem_context = "\n\n".join(
                [source_truth_block]
                # custom changes start
                + ([] if route_decision.get("intent_label") == "continuity_followup" and not references_past else common_parts)
                # custom changes end
                + [f"Recent conversation to summarize:\n{chr(10).join(mem_recent_lines)}"]
            )
            orch_context = self._trim_context(orch_context, max_chars=3000)  # reduced from 4800 — matches num_ctx=2048 (~3000 chars)
            mem_context = self._trim_context(mem_context, max_chars=2500)   # reduced from 4000

        results = {}
        memory_result = {}
        safety_data = {"risk": "low", "flagged_words": [], "issues": "none"}
        risk_level = "low"
        coach_tip = ""

        refine_output = ""

        # # --- P0 #1 + #2: True parallel execution with as_completed ---
        # with ThreadPoolExecutor(max_workers=4) as executor:
        #     future_to_agent = {}
        #     future_to_agent[executor.submit(self._call_agent, "orchestrator", user_text, orch_context)] = "orchestrator"
        #     if needs_memory_agent:
        #         future_to_agent[executor.submit(self._call_agent, "memory", user_text, mem_context)] = "memory"
        #     if needs_safety:
        #         future_to_agent[executor.submit(self._call_agent, "safety", user_text)] = "safety"

        #     coach_future = None
        #     for future in as_completed(future_to_agent):
        #         agent_name = future_to_agent[future]
        #         result = future.result()
        #         results[agent_name] = result or ""

        #         # When safety finishes, check if we need coach
        #         # if agent_name == "safety":
        #         #     safety_data = self._extract_json(results.get("safety", "")) or safety_data
        #         #     risk_level = str(safety_data.get("risk", "low")).lower()
        #         #     if risk_level == "high":
        #         #         coach_context = (
        #         #             f"User message: {user_text}\n"
        #         #             "Risk level: HIGH\n"
        #         #             f"Detected issues: {safety_data.get('issues', 'n/a')}"
        #         #         )
        #         #         coach_future = executor.submit(self._call_agent, "coach", coach_context)

        #         ##### changes by SB start #####
        #         if agent_name == "safety":
        #             safety_data = self._extract_json(results.get("safety", "")) or safety_data
        #             risk_level = str(safety_data.get("risk", "low")).lower()

        #             if risk_level == "high":
        #                 route_decision = {
        #                     "intent_label": "crisis",
        #                     "response_mode": "crisis_support",
        #                     "memory_needed": True,
        #                     "memory_types": ["profile"],
        #                     "escalation_flag": True,
        #                 }
        #                 coach_context = (
        #                     f"User message: {user_text}\n"
        #                     "Risk level: HIGH\n"
        #                     f"Detected issues: {safety_data.get('issues', 'n/a')}"
        #                 )
        #                 coach_future = executor.submit(self._call_agent, "coach", coach_context)

        #             elif risk_level == "medium":
        #                 route_decision["response_mode"] = "supportive_chat"
        #                 route_decision["escalation_flag"] = False
        #         ##### changes by SB end #####

        ##### changes by SB start #######
        # --- Final execution order: Safety -> Conditional Memory -> Orchestrator ---
        coach_future = None

        # 1) Safety first
        if needs_safety:
            results["safety"] = self._call_agent("safety", user_text) or ""
            safety_data = self._extract_json(results.get("safety", "")) or safety_data
            risk_level = str(safety_data.get("risk", "low")).lower()

            if risk_level == "high":
                route_decision = {
                    "intent_label": "crisis",
                    "response_mode": "crisis_support",
                    "memory_needed": "full",
                    "memory_types": ["current_session", "previous_sessions", "long_term_memory"],
                    "escalation_flag": True,
                }
            elif risk_level == "medium":
                route_decision["response_mode"] = "de_escalation_support"
                route_decision["escalation_flag"] = False
        # Recompute memory gating after safety may have changed the route decision
        memory_mode = str(route_decision.get("memory_needed", "false")).strip().lower()

        needs_memory_agent = (
            bool(memory_data)
            and memory_mode in ["light", "full"]
            and not is_trivial
        )

        # Rebuild deterministic recall only when memory is actually needed
        deterministic_recall = ""
        if needs_memory_agent:
            deterministic_recall = self._build_relevant_memory_recall(
                user_text,
                memory_data,
                min_score=3 if references_past else 5,
                allow_recent_fallback=references_past,
            )
        # 2) Memory only if route decision says it is needed
        if needs_memory_agent:
            # CRITICAL: When user is in crisis, give memory agent explicit instructions
            # to extract what CALMED THEM DOWN before and what helped them cope
            crisis_mem_context = mem_context
            if risk_level == "high":
                crisis_instructions = (
                    "\n\n=== CRITICAL CRISIS ANALYSIS INSTRUCTIONS ===\n"
                    "User is in HIGH RISK / CRISIS. Your memory_recall must extract:\n"
                    "1. PAST COPING STRATEGIES: What specific techniques helped calm this user in previous crises?\n"
                    "2. WHAT WORKED: Which approaches, words, or actions made them feel better before?\n"
                    "3. EMOTIONAL PATTERNS: What emotional progression did they go through? How long did recovery take?\n"
                    "4. THIS USER'S RESILIENCE: What shows they've gotten through difficult times before?\n"
                    "5. TONE THAT RESONATES: Does this user respond better to direct practical advice, empathy, humor, validation, or grounding techniques?\n"
                    "Provide these insights SPECIFICALLY so the coach can personalize the crisis response.\n"
                    "=== END CRISIS INSTRUCTIONS ===\n"
                )
                crisis_mem_context = crisis_instructions + mem_context
            results["memory"] = self._call_agent("memory", user_text, crisis_mem_context) or ""

        # 3) Add safety-aware instructions to the context passed to Coach
        orch_context_final = orch_context or ""

        if risk_level == "medium":
            orch_context_final = (
                "IMPORTANT SAFETY CONTEXT:\n"
                "User may be expressing anger or possible aggression. "
                "Respond with calm de-escalation. "
                "Do not validate harming anyone. "
                "Help the user pause, slow down, and create distance from the trigger if possible.\n\n"
                + orch_context_final
            )

        elif risk_level == "high":
            orch_context_final = (
                "IMPORTANT SAFETY CONTEXT:\n"
                "User may be in serious distress. Use supportive crisis language. "
                "Prioritize immediate safety and grounding.\n\n"
                + orch_context_final
            )

        continuity_only_context = (
            f"{source_truth_block}\n\n"
            f"LATEST USER MESSAGE:\n{user_text}\n\n"
            "Instructions:\n"
            "- Answer only from the source-of-truth turns above.\n"
            "- If the user asks about your last sentence or last reply, use the immediately previous assistant turn if it is available.\n"
            "- If the previous sentence was incomplete, complete or restate only the unfinished thought.\n"
            "- Prefer a shorter complete answer over a longer unfinished one, and end with a complete sentence.\n"
            "- Do not ask a clarifying question first when the relevant prior turn is already available above.\n"
            "- For very short replies like 'continue', 'go on', 'tell me more', or 'yes acknowledge', continue the previous conversational act from the current session.\n"
            "- Do not broaden the discussion or introduce a new topic.\n"
            "- Do not generalize beyond the quoted current-session turns.\n"
            "- Do not use onboarding, emotional history, previous sessions, or long-term memory.\n"
            "- If the exact detail is missing, say that briefly.\n"
        )
        # custom changes start: when user references past sessions, include full context with session history
        if route_decision.get("intent_label") == "continuity_followup" and references_past:
            # User is asking about previous session - use FULL context with memory data.
            # Same empty-context gap as the "else" branch below: if memory wasn't
            # actually fetched (e.g. memory_data was empty), orch_context_final is ""
            # even though the user explicitly referenced the past — fall back to the
            # always-on session-buffer block rather than giving the Coach nothing.
            coach_relevant_context = orch_context_final or source_truth_block
        elif route_decision.get("intent_label") == "continuity_followup" and not references_past:
            # Current session continuity - use only current turns
            coach_relevant_context = continuity_only_context or source_truth_block
        else:
            # All other intents - use full context. When the router decided memory
            # wasn't needed, orch_context_final is empty — fall back to the always-on
            # session-buffer block so the Coach still has real, grounded conversation
            # history instead of nothing (which is what let it invent false memories).
            coach_relevant_context = orch_context_final or source_truth_block
        # custom changes end

        # custom changes start: Add special instruction when user references past sessions
        coach_instructions = ""
        if route_decision.get("intent_label") == "continuity_followup" and references_past:
            coach_instructions = (
                "IMPORTANT: The user is asking about a PREVIOUS SESSION conversation.\n"
                "- Reference SPECIFIC details from the previous session memory provided below (dates, topics, emotions).\n"
                "- Do NOT say 'I remember you shared something' — instead, cite the actual topics/dates from memory.\n"
                "- Use the session summaries and facts to reconstruct what was discussed.\n"
                "- Make your response personalized and specific to what they discussed before.\n\n"
            )

        # Add trusted adult info if risk is extreme (crisis intervention)
        trusted_adult_info = ""
        if risk_level == "extreme":
            try:
                from database import fetch_trusted_adult_info
                trusted_adult_data = fetch_trusted_adult_info(user_id) or {}
                trusted_name = trusted_adult_data.get("trusted_adult_name", "").strip()
                if trusted_name:
                    trusted_adult_info = f"\nTRUSTED ADULT TO CONTACT: {trusted_name}"
                else:
                    trusted_adult_info = "\nNO TRUSTED ADULT PROVIDED - User should contact close family/friends immediately"
            except Exception as e:
                logger.warning(f"Could not fetch trusted adult info: {e}")
                trusted_adult_info = "\nCould not load trusted adult info - direct user to contact close family"

        coach_context = (
            f"{coach_instructions}"
            f"USER MESSAGE:\n{user_text}\n\n"
            f"RISK LEVEL: {risk_level}\n"
            f"SAFETY ACTION: {'immediate' if risk_level == 'high' else 'supportive' if risk_level == 'medium' else 'normal'}\n"
            f"INTENT LABEL: {route_decision.get('intent_label', 'general_chat')}\n"
            f"RESPONSE MODE: {route_decision.get('response_mode', 'normal_chat')}\n"
            f"MEMORY NEEDED: {route_decision.get('memory_needed', 'false')}\n"
            f"MEMORY TYPES: {', '.join(route_decision.get('memory_types', [])) if route_decision.get('memory_types') else 'none'}\n"
            f"{trusted_adult_info}\n\n"
            f"RELEVANT USER CONTEXT:\n{coach_relevant_context}"
        )
        # custom changes end

        # Guardrail: never let the model confirm a specific "do you remember X" claim
        # unless X is actually grounded in the real context it was just handed. Only
        # eligible when risk is low — a crisis turn must always go through the full
        # Coach/safety handling, never a canned short-circuit reply.
        unverified_topic = None
        if risk_level == "low":
            unverified_topic = self._find_unverified_recall_topic(user_text, coach_relevant_context)

        if unverified_topic:
            template = _HONEST_NO_RECALL_TEMPLATES[self.message_count % len(_HONEST_NO_RECALL_TEMPLATES)]
            coach_tip = template.format(topic=unverified_topic)
            logger.info("Recall guardrail fired: topic=%r not found in available context — skipped LLM call", unverified_topic)
        else:
            coach_tip = self._call_agent("coach", user_text, coach_context, risk_level=risk_level) or ""
        results["coach"] = coach_tip

        # Process memory result
        memory_has_contribution = False
        memory_result = {}
        if "memory" in results:
            memory_result = self._extract_json(results.get("memory", ""))
            if memory_result:
                # Normalize key variants emitted by smaller models.
                if "topic_lock" not in memory_result and "topic_state.locked" in memory_result:
                    topic_lock_raw = memory_result.get("topic_state.locked")
                    if isinstance(topic_lock_raw, bool):
                        memory_result["topic_lock"] = topic_lock_raw
                    elif isinstance(topic_lock_raw, str):
                        memory_result["topic_lock"] = topic_lock_raw.strip().lower() in {"1", "true", "yes", "on"}
                if "new_fact" not in memory_result and isinstance(memory_result.get("new_facts"), dict):
                    memory_result["new_fact"] = memory_result.get("new_facts") or {}

            # Check if memory agent had a meaningful contribution
            # (not just "No" or empty response)
            memory_recall_raw = memory_result.get("memory_recall", "") if memory_result else ""
            memory_recall = ""
            if isinstance(memory_recall_raw, str):
                cleaned_recall = memory_recall_raw.strip()
                if cleaned_recall.lower() not in ("", "null", "none", "n/a"):
                    memory_recall = cleaned_recall
            elif memory_recall_raw:
                memory_recall = str(memory_recall_raw).strip()

            new_facts_raw = memory_result.get("new_fact", {}) if memory_result else {}
            if isinstance(new_facts_raw, str):
                parsed_inline = self._extract_json(new_facts_raw)
                if parsed_inline:
                    new_facts_raw = parsed_inline
                else:
                    try:
                        decoded = json.loads(new_facts_raw)
                        new_facts_raw = decoded if isinstance(decoded, dict) else {}
                    except Exception:
                        new_facts_raw = {}
            if not isinstance(new_facts_raw, dict):
                new_facts_raw = {}
            if new_facts_raw:
                memory_result["new_fact"] = new_facts_raw

            # Memory is meaningful if it provided actual recall text OR discovered facts
            memory_has_contribution = bool(memory_recall) or bool(new_facts_raw)

            # If memory didn't contribute meaningfully, reset to prevent merging empty data
            if not memory_has_contribution:
                memory_result = {}  # This prevents extraction of empty facts below

        # fallback_text = (
        #     "I hear how urgent this feels. I can still help right now: share your target role and city, "
        #     "and I will give you a concrete job-search plan for today."
        # )
        ### changes by SB start ###
        main_reply = self._sanitize_reply_text(results.get("coach", ""))
        if not main_reply:
            main_reply = fallback_text
        is_fallback = main_reply == fallback_text
        ### changes by SB end #######

        if is_fallback:
            logger.error(
                "FALLBACK TRIGGERED: Coach returned None/empty. "
                "User: %s | needs_safety=%s | results_keys=%s | safety_risk=%s",
                user_text[:60], needs_safety, list(results.keys()), risk_level
            )
            for agent_name, agent_result in results.items():
                if agent_result:
                    preview = str(agent_result)[:80].replace("\n", " ")
                    logger.info("  Agent '%s' output: %s", agent_name, preview)
                else:
                    logger.warning("  Agent '%s' returned EMPTY/None", agent_name)

        # # Wait for coach if submitted
        # if coach_future is not None:
        #     coach_result = coach_future.result()
        #     coach_tip = coach_result or ""

        coach_tip = self._sanitize_reply_text(coach_tip)

        recall_text = deterministic_recall or memory_result.get("memory_recall") or ""
        if recall_text:
            memory_result["memory_recall"] = recall_text

        new_facts = memory_result.get("new_fact", {})
        if isinstance(new_facts, str):
            try:
                new_facts = json.loads(new_facts)
            except Exception:
                new_facts = {}
        if not isinstance(new_facts, dict):
            new_facts = {}

        topic = (memory_result.get("current_topic") or "").strip()
        if topic:
            new_facts["topic_state"] = {"current_topic": topic, "locked": bool(memory_result.get("topic_lock", True))}

        session_title = str(memory_result.get("session_title", "")).strip()
        if session_title:
            session_title = session_title.strip('"').strip("'").strip("*")
            for prefix in ["session title:", "title:", "topic:", "summary:"]:
                if session_title.lower().startswith(prefix):
                    session_title = session_title[len(prefix):].strip()
            session_title = " ".join(session_title.split())
        if not session_title or len(session_title) < 3:
            session_title = (topic or user_text[:60]).strip() or "General conversation"

        session_summary = str(memory_result.get("session_summary", "")).strip()
        if session_summary:
            session_summary = " ".join(session_summary.split())
        if len(session_summary) < 20:
            session_summary = self._build_structured_summary(user_text, memory_result.get("tone", ""), topic, new_facts, recall_text)

        # safety_action = "none"
        # agent_coach_active = "No"
        # if risk_level == "high":
        #     safety_action = "coach activated - high-risk support provided"
        #     agent_coach_active = "Yes" if coach_tip else "No"
        # elif risk_level == "medium":
        #     safety_action = "monitoring - concerning patterns noted"

        safety_action = "normal"
        agent_coach_active = "Yes" if coach_tip else "No"

        if risk_level == "high":
            safety_action = "immediate"
        elif risk_level == "medium":
            safety_action = "supportive"
        else:
            safety_action = "normal"

        final_response = main_reply #f"{main_reply}\n\n{coach_tip}" if coach_tip else main_reply

        self._session_buffer.append((user_text, final_response))
        self._session_buffer = self._session_buffer[-30:]

        if self._reply_has_question(final_response):
            self.ask_question_cooldown = 2
        elif self.ask_question_cooldown > 0:
            self.ask_question_cooldown -= 1
        self._persist_runtime_state()

        pipeline_elapsed = time.time() - pipeline_start
        logger.info(
            "Pipeline COMPLETE in %.2fs: is_fallback=%s | risk=%s | safety=%s | reply_len=%d",
            pipeline_elapsed, is_fallback, risk_level, safety_action, len(final_response)
        )

        memory_mode = str(route_decision.get("memory_needed", "false")).strip().lower()

        # custom changes start
        # Compute which memory types were actually used (not just planned by router).
        actual_memory_types = []
        if memory_data and needs_memory_agent:
            # current_session: session buffer or recent DB messages were available
            if memory_data.get("recent_messages") or self._session_buffer:
                actual_memory_types.append("current_session")
            # long_term_memory: past-session summary or facts exist and history is present
            if memory_data.get("has_history") and (
                memory_data.get("summary") or memory_data.get("facts") or memory_data.get("user_memory")
            ):
                actual_memory_types.append("long_term_memory")
            # onboarding_profile: onboarding answers were loaded
            if memory_data.get("onboarding"):
                actual_memory_types.append("onboarding_profile")
            # rag_documents: RAG retrieval returned chunks
            if memory_data.get("rag_context"):
                actual_memory_types.append("rag_documents")
        memory_types_list = actual_memory_types
        # custom changes end

        analysis_data = {
            "risk": risk_level,
            "flagged_words": safety_data.get("flagged_words", []),
            "issues": safety_data.get("issues", "none"),
            "safety": safety_action,
            "tone": memory_result.get("tone", "neutral"),
            "new_facts": new_facts,
            "memory_recall": recall_text or None,
            "new_summary": session_summary,
            "session_title": session_title[:80],

            # Legacy compatibility fields
            "agent_safety": "Yes" if needs_safety else "No",
            "agent_memory": "Yes" if needs_memory_agent else "No",
            "agent_orchestrator": "Yes" if results.get("orchestrator") else "No",
            "agent_coach": agent_coach_active,
            "agent_safety_output": results.get("safety", "") if needs_safety else "",
            "agent_memory_raw_output": results.get("memory", "") if needs_memory_agent else "",
            "agent_memory_output": self._extract_memory_message(results.get("memory", "")) if needs_memory_agent else "",
            "agent_orchestrator_output": results.get("orchestrator", ""),
            "agent_refine_output": refine_output,
            "agent_coach_output": coach_tip or "",
            "is_fallback": is_fallback,

            # Contribution + source tracking
            "memory_has_contribution": memory_has_contribution,
            "reply_source_agent": "fallback" if is_fallback else "coach",

            # New locked-architecture fields
            "risk_level": risk_level,
            "safety_action": safety_action,
            "intent_label": route_decision["intent_label"],
            "response_mode": route_decision["response_mode"],
            "memory_needed": memory_mode,
            "memory_types": memory_types_list,
            "memory_used": bool(memory_has_contribution or memory_mode in ["light", "full"]),
            "memory_type": ", ".join(memory_types_list) if memory_types_list else "",
            "escalation_flag": bool(route_decision["escalation_flag"]),
            "final_reply_agent": "fallback" if is_fallback else "coach",
            "fallback_triggered": is_fallback,

            # Read by evaluations/latency_benchmark.py. agent_s is a copy,
            # not a reference, so later pipeline calls on the same engine
            # instance can't retroactively mutate a previous call's result.
            "latency": {
                "pipeline_s": round(pipeline_elapsed, 3),
                "agent_s": dict(self._agent_timings),
            },
        }
        return final_response, "Multi-Agent", analysis_data
