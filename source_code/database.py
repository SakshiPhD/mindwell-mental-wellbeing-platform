"""
Database functions for MindWell application.
Handles all PostgreSQL database operations including user management,
chat storage, and memory/analysis functions.
"""
import streamlit as st
import psycopg2
from psycopg2 import errors, pool as pg_pool, extensions
import json
import ast
import re
import atexit
import threading
import logging
import uuid
import time
import hashlib
import os
import toml
from contextlib import contextmanager
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _load_db_credentials():
    """Return Postgres credentials as a dict with keys: host, database, user,
    password, port, sslmode — or None if none of the sources below have them.

    st.secrets resolves .streamlit/secrets.toml relative to the process's
    current working directory. That silently breaks DB connectivity if the
    app is launched with a different working directory than expected — both
    `cd source_code && streamlit run app.py` (documented in the setup guide)
    and `streamlit run source_code/app.py` from the project root are valid
    ways to start this app, but only the second one actually finds the
    secrets file. Reading the file directly from a location anchored to this
    module fixes that regardless of how the app was launched.

    Resolution order:
      1. .streamlit/secrets.toml read directly, anchored to this file's
         location (works regardless of current working directory).
      2. st.secrets["postgres"] — covers managed deployments (e.g. Streamlit
         Community Cloud) where secrets are injected without a physical file
         at a predictable path.
      3. Environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER,
         DB_PASSWORD, DB_SSLMODE) — the .env-based configuration the
         project's own setup docs describe, previously unsupported by code.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        secrets_path = os.path.abspath(os.path.join(here, "..", ".streamlit", "secrets.toml"))
        if os.path.isfile(secrets_path):
            with open(secrets_path, "r") as f:
                parsed = toml.load(f)
            pg = parsed.get("postgres")
            if pg and pg.get("host") and pg.get("database") and pg.get("user"):
                return {
                    "host": pg["host"],
                    "database": pg["database"],
                    "user": pg["user"],
                    "password": pg.get("password", ""),
                    "port": pg.get("port", 5432),
                    "sslmode": pg.get("sslmode", "require"),
                }
    except Exception as e:
        logger.warning("Could not read .streamlit/secrets.toml directly: %s", _compact_error(e))

    try:
        pg = st.secrets["postgres"]
        if pg.get("host") and pg.get("database") and pg.get("user"):
            return {
                "host": pg["host"],
                "database": pg["database"],
                "user": pg["user"],
                "password": pg.get("password", ""),
                "port": pg.get("port", 5432),
                "sslmode": pg.get("sslmode", "require"),
            }
    except Exception:
        pass

    if os.getenv("DB_HOST") and os.getenv("DB_NAME") and os.getenv("DB_USER"):
        return {
            "host": os.getenv("DB_HOST"),
            "database": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD", ""),
            "port": os.getenv("DB_PORT", "5432"),
            "sslmode": os.getenv("DB_SSLMODE", "require"),
        }

    return None


def _should_use_rag(query: str) -> bool:
    """
    Determine if RAG retrieval is beneficial for this query.
    Avoids wasting compute on simple greetings, confirmations, and short messages.

    Returns: True if query has enough semantic content to warrant RAG search
    """
    if not query or not isinstance(query, str):
        return False

    query_clean = query.strip().lower()

    # Skip very short messages (insufficient semantic content)
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

    # Skip if message is mostly punctuation/emojis (no actual content)
    alphanumeric_count = sum(1 for c in query_clean if c.isalnum())
    if alphanumeric_count < len(query_clean) * 0.5:  # less than 50% alphanumeric
        return False

    return True

# ===================== CONNECTION POOLING =====================

_pool = None
_pool_lock = threading.Lock()
_MAX_POOL_HEALTHCHECK_ATTEMPTS = 2

# Per-session threading locks to prevent concurrent finalize_session_analysis calls
# for the same session within the same process — root cause of the deadlock.
# Two overlapping finalizations create a lock-ordering conflict between
# chat_analysis and chat_messages tables, causing PostgreSQL to abort one of them.
_finalize_session_locks: dict = {}
_finalize_session_locks_guard = threading.Lock()
_POOL_BYPASS_SECONDS = 30
_pool_bypass_until = 0.0
_STALE_CONNECTION_MARKERS = (
    "ssl syscall error",
    "could not receive data from server",
    "server closed the connection unexpectedly",
    "connection not open",
    "connection already closed",
    "broken pipe",
    "connection reset by peer",
    "software caused connection abort",
)


def _compact_error(err, max_len=240):
    """Return a single-line compact error string for logs."""
    text = " ".join(str(err or "").split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _pool_bypass_active():
    """Whether pooled connections should be skipped temporarily."""
    return time.monotonic() < _pool_bypass_until


def _activate_pool_bypass():
    """Temporarily bypass pooling after repeated stale socket failures."""
    global _pool_bypass_until
    _pool_bypass_until = time.monotonic() + _POOL_BYPASS_SECONDS


def _connect_direct():
    """Create a one-off direct DB connection as a fallback path."""
    try:
        creds = _load_db_credentials()
        if not creds:
            raise RuntimeError("No database credentials found (checked secrets.toml, st.secrets, and env vars)")
        return psycopg2.connect(
            host=creds["host"],
            database=creds["database"],
            user=creds["user"],
            password=creds["password"],
            port=creds["port"],
            sslmode=creds.get("sslmode", "require"),
            connect_timeout=10,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
    except Exception as e:
        logger.error("Failed to create direct DB connection fallback: %s", _compact_error(e))
        return None


def _get_pool():
    """Lazily initialize a thread-safe connection pool (singleton)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    creds = _load_db_credentials()
                    if not creds:
                        raise RuntimeError("No database credentials found (checked secrets.toml, st.secrets, and env vars)")
                    _pool = pg_pool.ThreadedConnectionPool(
                        2, 10,
                        host=creds["host"],
                        database=creds["database"],
                        user=creds["user"],
                        password=creds["password"],
                        port=creds["port"],
                        sslmode=creds.get("sslmode", "require"),
                        connect_timeout=10,
                        keepalives=1,
                        keepalives_idle=30,
                        keepalives_interval=10,
                        keepalives_count=3,
                    )
                    atexit.register(_close_pool)
                except Exception as e:
                    logger.error("Failed to create connection pool: %s", _compact_error(e))
                    return None
    return _pool


def _close_pool():
    """Close all pooled connections on process exit."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception:
            pass
        _pool = None


def _reset_pool():
    """Recreate the pooled connections after repeated stale socket failures."""
    global _pool
    old_pool = None
    with _pool_lock:
        old_pool = _pool
        _pool = None
    if old_pool is not None:
        try:
            old_pool.closeall()
        except Exception:
            pass
    return _get_pool()


def _is_stale_connection_error(err):
    """Identify low-level socket/SSL disconnect signatures."""
    message = str(err or "").lower()
    return any(marker in message for marker in _STALE_CONNECTION_MARKERS)


def _discard_connection(pool, conn):
    """Return connection to pool as closed so it is not reused."""
    if conn is None:
        return
    try:
        pool.putconn(conn, close=True)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _return_connection(pool, conn):
    """Return healthy connection to pool."""
    if conn is None:
        return
    try:
        pool.putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _connection_is_healthy(conn):
    """Verify pooled connection can run a lightweight roundtrip."""
    if conn is None or getattr(conn, "closed", 1) != 0:
        return False
    try:
        tx_status = conn.get_transaction_status()
        if tx_status != extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
        if _is_stale_connection_error(err):
            _activate_pool_bypass()
        logger.warning("Discarding unusable pooled DB connection: %s", _compact_error(err))
        return False
    except Exception as err:
        logger.warning("Discarding pooled DB connection after failed health check: %s", _compact_error(err))
        return False


def _borrow_healthy_connection(pool):
    """Borrow connection, replacing stale sockets when needed."""
    for attempt in range(1, _MAX_POOL_HEALTHCHECK_ATTEMPTS + 1):
        try:
            conn = pool.getconn()
        except Exception as err:
            logger.error("Unable to borrow DB connection from pool: %s", _compact_error(err))
            return None

        if _connection_is_healthy(conn):
            return conn

        logger.warning(
            "Discarding stale pooled DB connection (attempt %d/%d)",
            attempt,
            _MAX_POOL_HEALTHCHECK_ATTEMPTS,
        )
        _discard_connection(pool, conn)
        if _pool_bypass_active():
            return None
    return None


@contextmanager
def get_pooled_connection():
    """Context manager that borrows a connection from the pool and auto-returns it."""
    pool = _get_pool()
    conn = None
    using_pool = False

    if pool is not None and not _pool_bypass_active():
        conn = _borrow_healthy_connection(pool)
        if conn is None:
            logger.warning("Rebuilding DB pool after stale connection attempts.")
            pool = _reset_pool()
            if pool is not None:
                conn = _borrow_healthy_connection(pool)
            if conn is None:
                _activate_pool_bypass()
                logger.warning(
                    "Temporarily bypassing DB pool for %ds after repeated stale socket failures.",
                    _POOL_BYPASS_SECONDS,
                )
        using_pool = conn is not None

    if conn is None:
        conn = _connect_direct()
        using_pool = False

    if conn is None:
        yield None
        return

    should_discard = False
    try:
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as err:
        should_discard = True
        if _is_stale_connection_error(err):
            _activate_pool_bypass()
            logger.warning("Detected stale DB connection during query: %s", _compact_error(err))
        raise
    except Exception:
        if getattr(conn, "closed", 1) != 0:
            should_discard = True
        raise
    finally:
        if using_pool:
            if should_discard or getattr(conn, "closed", 1) != 0:
                _discard_connection(pool, conn)
            else:
                try:
                    if conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
                        conn.rollback()
                except Exception:
                    _discard_connection(pool, conn)
                else:
                    _return_connection(pool, conn)
        else:
            try:
                if conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
                    conn.rollback()
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass


# ===================== DATA CLEANING UTILITIES =====================

GENERIC_FACT_KEYS = {
    "fact", "facts", "info", "information", "detail", "details", "issue",
    "issues", "problem", "problems", "context", "update", "status", "note", "key", "value",
}

TRIVIAL_USER_INPUTS = {
    "hi", "hello", "hey", "hii", "hie", "yo", "sup",
    "good morning", "good evening", "good night",
    "ok", "okay", "sure", "fine", "yeah", "yep", "nah", "nope",
    "lol", "haha", "hmm", "cool", "thanks", "thank you", "ty",
    "got it", "alright", "k", "kk", "true", "right",
}

SEARCH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "has", "was", "were",
    "are", "you", "your", "about", "from", "what", "when", "where", "how",
    "still", "same", "just", "again", "did", "our", "into", "been", "over",
}


def _extract_search_keywords(text, limit=8):
    """Extract stable search keywords for relevance-based DB retrieval."""
    tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
    keys = []
    for tok in tokens:
        if len(tok) <= 2 or tok in SEARCH_STOPWORDS:
            continue
        if tok not in keys:
            keys.append(tok)
        if len(keys) >= limit:
            break
    return keys


def _parse_json_like(text):
    """Parse JSON or Python-literal JSON-ish strings to dict/list, else None."""
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None
    if not ((raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]"))):
        return None
    try:
        return json.loads(raw)
    except Exception:
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            return None
    return None


def _coerce_session_id(session_id):
    """Normalize session_id to canonical UUID string; return None if invalid."""
    if session_id is None:
        return None
    raw = str(session_id).strip()
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except Exception:
        return None


def _normalize_fact_value(value, depth=0):
    """Normalize fact payload values recursively while preserving structured data."""
    if depth > 6 or value is None:
        return None

    if isinstance(value, str):
        compact = " ".join(value.strip().split())
        if not compact or compact.lower() in ("null", "none", "n/a", "unknown", "undefined"):
            return None
        parsed = _parse_json_like(compact)
        if parsed is not None:
            return _normalize_fact_value(parsed, depth + 1)
        if len(compact) > 300:
            compact = compact[:297] + "..."
        return compact

    if isinstance(value, dict):
        cleaned = {}
        for key, nested in value.items():
            clean_key = re.sub(r"[^a-z0-9_]", "", str(key).lower().strip().replace(" ", "_").replace("-", "_"))
            if not clean_key or clean_key in GENERIC_FACT_KEYS:
                continue
            normalized_nested = _normalize_fact_value(nested, depth + 1)
            if normalized_nested is None:
                continue
            cleaned[clean_key] = normalized_nested
        return cleaned or None

    if isinstance(value, list):
        normalized_items = []
        for item in value[:12]:
            normalized_item = _normalize_fact_value(item, depth + 1)
            if normalized_item is None:
                continue
            normalized_items.append(normalized_item)
        return normalized_items or None

    if isinstance(value, (int, float, bool)):
        return value

    compact = " ".join(str(value).strip().split())
    if not compact:
        return None
    if len(compact) > 300:
        compact = compact[:297] + "..."
    return compact


def _facts_equal(left, right):
    """Robust equality check for nested fact values."""
    try:
        return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)
    except Exception:
        return str(left).strip().lower() == str(right).strip().lower()


def _coerce_facts_payload(raw_facts):
    """Coerce DB/user payload into a normalized dict facts object."""
    if raw_facts is None:
        return {}

    parsed = raw_facts
    if isinstance(raw_facts, str):
        parsed = _parse_json_like(raw_facts)
        if parsed is None:
            try:
                parsed = json.loads(raw_facts)
            except Exception:
                parsed = {}

    normalized = _normalize_fact_value(parsed)
    return normalized if isinstance(normalized, dict) else {}


def clean_facts(raw_facts, existing_facts=None):
    """Validate and clean new_fact JSON before saving.
    
    - Removes empty/null keys and values
    - Normalizes keys to snake_case descriptive format
    - Deduplicates against existing facts
    - Returns clean dict ready for DB storage
    """
    if not raw_facts:
        return {}

    legacy_key_raw = raw_facts.get("key") if isinstance(raw_facts, dict) else None
    legacy_value_raw = raw_facts.get("value") if isinstance(raw_facts, dict) else None

    cleaned = {}
    existing = _coerce_facts_payload(existing_facts) if existing_facts else {}

    # Common legacy model pattern: {"key":"sleep_goal","value":"7 hours"}
    if isinstance(legacy_key_raw, str):
        lk = re.sub(r"[^a-z0-9_]", "", legacy_key_raw.lower().strip().replace(" ", "_").replace("-", "_"))
        lv = _normalize_fact_value(legacy_value_raw)
        if lk and lk not in GENERIC_FACT_KEYS and len(lk) >= 3 and lv is not None:
            if lk not in existing or not _facts_equal(existing.get(lk), lv):
                cleaned[lk] = lv

    normalized_input = _coerce_facts_payload(raw_facts)
    if not normalized_input:
        return cleaned

    for key, value in normalized_input.items():
        if key in ("key", "value"):
            continue
        clean_key = re.sub(r"[^a-z0-9_]", "", str(key).lower().strip().replace(" ", "_").replace("-", "_"))
        if not clean_key:
            continue
        if clean_key in GENERIC_FACT_KEYS or len(clean_key) < 3:
            continue

        clean_value = _normalize_fact_value(value)
        if clean_value is None:
            continue

        # Skip if identical to existing fact
        if clean_key in existing and _facts_equal(existing[clean_key], clean_value):
            continue

        cleaned[clean_key] = clean_value

    # Schema-bucket mapping: route known patterns into stable buckets
    BUCKET_KEYWORDS = {
        "preferences": ["prefer", "like", "dislike", "favorite", "reply_length", "style"],
        "goals": ["goal", "target", "plan", "aspire", "want_to", "aim"],
        "routines": ["routine", "schedule", "habit", "morning", "evening", "daily", "weekly"],
        "stressors": ["stress", "trigger", "worry", "anxiety", "fear", "pressure", "conflict"],
        "coping_tools": ["coping", "relax", "meditat", "exercise", "journal", "breathing", "therapy"],
    }
    bucketed = {}
    for ck, cv in cleaned.items():
        # Preserve topic_state as-is (injected by engine)
        if ck == "topic_state":
            if isinstance(cv, str):
                parsed_topic = _parse_json_like(cv)
                if isinstance(parsed_topic, dict):
                    cv = parsed_topic
            bucketed[ck] = cv
            continue

        # Try to map into a bucket
        mapped = False
        combined = f"{ck} {str(cv)}".lower()
        for bucket, keywords in BUCKET_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                if ck == bucket:
                    bucketed[bucket] = cv
                else:
                    current = bucketed.get(bucket)
                    if not isinstance(current, dict):
                        current = {} if current is None else {"value": current}
                    current[ck] = cv
                    bucketed[bucket] = current
                mapped = True
                break
        if not mapped:
            # Keep descriptive keys as-is (avoid data loss)
            bucketed[ck] = cv

    return bucketed


def clean_summary(raw_summary, user_input=""):
    """Clean and validate high-information session summary before saving."""
    if not raw_summary or not isinstance(raw_summary, str):
        if user_input:
            return user_input[:220].strip() + ("..." if len(user_input) > 220 else "")
        return "General conversation"
    
    summary = raw_summary.strip()
    
    prefixes_to_strip = [
        'summary:', 'session summary:', 'topic:', 'session title:',
        'title:', 'session:', 'current topic:', 'response:', 'analysis:'
    ]
    for prefix in prefixes_to_strip:
        if summary.lower().startswith(prefix):
            summary = summary[len(prefix):].strip()
    
    summary = summary.strip('"').strip("'").strip('*').strip('`').strip()
    
    summary = ' '.join(summary.split())

    if summary.startswith("{") or summary.endswith("}"):
        summary = ""
    if summary.count(":") >= 3 and len(summary.split()) < 12:
        summary = ""
    
    if len(summary) < 20 or summary.lower() in ('...', 'n/a', 'none', 'null', 'undefined'):
        if user_input:
            return user_input[:220].strip() + ("..." if len(user_input) > 220 else "")
        return "General conversation"
    
    # Keep rich summaries but cap to avoid context bloat.
    if len(summary) > 900:
        summary = summary[:897] + "..."
    
    return summary


def _is_trivial_input(text):
    """Return True when text is too short/casual to replace an existing summary."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    return normalized in TRIVIAL_USER_INPUTS or len(normalized.split()) <= 2


def _is_high_information_summary(text):
    """Detect whether a summary has enough signal to be reused as primary context."""
    summary = " ".join(str(text or "").split()).strip()
    if not summary:
        return False
    if len(summary) < 20:
        return False
    return summary.lower() not in TRIVIAL_USER_INPUTS


def _summary_snippet(text, max_len=120):
    """Build a compact, quote-safe snippet for summary text."""
    snippet = " ".join(str(text or "").split()).strip()
    if not snippet:
        return ""
    snippet = snippet.replace("'", "").replace('"', "")
    if len(snippet) > max_len:
        snippet = snippet[:max_len - 3].rstrip() + "..."
    return snippet


def _agent_was_active(payload):
    """Return True when an agent payload indicates meaningful participation."""
    text = str(payload or "").strip().lower()
    return bool(text) and text not in {"no", "none", "null", "n/a", "false", "0", "{}"}


def _collect_unique_points(messages, max_points=3, max_len=100, min_words=3):
    """Collect deduplicated message snippets for summary sentences."""
    points = []
    seen = set()
    for msg in messages:
        point = _summary_snippet(msg, max_len=max_len)
        key = point.lower()
        if not point or key in seen or len(point.split()) < min_words:
            continue
        seen.add(key)
        points.append(point)
        if len(points) >= max_points:
            break
    return points


def _join_phrases(parts):
    """Join phrases into a human-readable list."""
    items = [str(p).strip() for p in parts if str(p).strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _infer_user_topics(meaningful_messages):
    """Infer high-level user discussion themes from session text."""
    text = " ".join(meaningful_messages).lower()
    topic_rules = [
        (("exam", "study", "syllabus", "revision", "test", "assignment", "placement"), "exam pressure and study-load management"),
        (("work", "job", "internship", "office", "deadline", "manager", "boss"), "work pressure and time management"),
        (("sleep", "insomnia", "tired", "fatigue", "exhausted"), "sleep disruption and fatigue"),
        (("anxious", "anxiety", "panic", "worried", "worry", "overthink"), "anxiety and recurring worry"),
        (("focus", "concentrate", "procrast", "distract", "consisten", "routine"), "difficulty maintaining focus and consistency"),
        (("relationship", "family", "friend", "parents", "partner"), "relationship or family-related stress"),
        (("sad", "low", "hopeless", "empty", "overwhelmed", "stressed"), "emotional strain and stress symptoms"),
    ]
    topics = []
    for keywords, phrase in topic_rules:
        if any(token in text for token in keywords):
            topics.append(phrase)
    return topics[:3]


def _contains_any(text, markers):
    blob = str(text or "").lower()
    return any(marker in blob for marker in markers)


def _infer_session_outcome(user_messages):
    """Infer whether the discussion seems resolved, partial, or unresolved."""
    text = " ".join(user_messages).lower()
    unresolved_markers = (
        "dont understand", "don't understand", "didnt get", "didn't get",
        "not clear", "still confused", "what is this", "what to do",
        "how to do", "why", "umm", "wtf", "shi", "stuck",
    )
    resolved_markers = (
        "got it", "understood", "makes sense", "clear now", "thanks",
        "thank you", "helped", "okay got it", "alright got it",
    )

    has_unresolved = _contains_any(text, unresolved_markers)
    has_resolved = _contains_any(text, resolved_markers)

    if has_unresolved and has_resolved:
        return "The discussion was partially clarified, but some points still appear unresolved."
    if has_unresolved:
        return "The discussion remained unresolved and likely needs a concrete next-step plan."
    if has_resolved:
        return "The user indicated that the main concern was clarified in this session."
    if len(user_messages) <= 2:
        return "The outcome is still uncertain because the session remained brief."
    return "The discussion appears partially clarified, with follow-up likely needed."


def _assistant_had_connection_issue(assistant_messages):
    """Detect if assistant outputs indicate degraded responses due to technical issues."""
    text = " ".join(assistant_messages).lower()
    markers = (
        "connection issue",
        "unable to respond effectively",
        "trouble collecting my thoughts",
        "missed that due to a glitch",
        "something went wrong on my end",
    )
    return any(marker in text for marker in markers)


_RISK_PRIORITY = {"low": 0, "medium": 1, "high": 2}


def _normalize_risk(risk, default="low"):
    """Normalize risk labels into low/medium/high."""
    value = str(risk or "").strip().lower()
    if value in _RISK_PRIORITY:
        return value
    return default


def _max_risk(*values):
    """Pick highest-risk value among candidates."""
    best = "low"
    for value in values:
        current = _normalize_risk(value, default="low")
        if _RISK_PRIORITY[current] > _RISK_PRIORITY[best]:
            best = current
    return best


def _infer_tone_from_user_messages(user_messages):
    """Heuristic tone fallback when no explicit memory tone is available."""
    text = " ".join(str(m or "").lower() for m in user_messages)
    if not text.strip():
        return "neutral"
    if any(tok in text for tok in ("panic", "anxious", "anxiety", "overthink", "worried", "worry")):
        return "anxious"
    if any(tok in text for tok in ("sad", "empty", "hopeless", "down", "low", "cry")):
        return "sad"
    if any(tok in text for tok in ("angry", "frustrated", "irritated", "annoyed")):
        return "frustrated"
    if any(tok in text for tok in ("stressed", "stress", "pressure", "overwhelmed", "burnout")):
        return "stressed"
    if any(tok in text for tok in ("tired", "fatigue", "exhausted", "sleep")):
        return "tired"
    if any(tok in text for tok in ("better", "calm", "okay now", "feeling good", "hopeful")):
        return "hopeful"
    return "neutral"


def _parse_json_dict(payload):
    """Best-effort parse for JSON-like payloads emitted by agents."""
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        return None
    parsed = _parse_json_like(payload)
    return parsed if isinstance(parsed, dict) else None


def _extract_facts_from_messages(user_messages):
    """Extract key facts (stressors, coping strategies, patterns) from user messages."""
    facts = {}
    combined_text = " ".join(user_messages).lower()

    # Stressors & Concerns
    stressor_keywords = {
        "work": ["work", "job", "boss", "colleague", "deadline", "project", "office", "workload"],
        "relationships": ["relationship", "partner", "spouse", "family", "friend", "mother", "father", "sister", "brother", "argue", "fight", "conflict"],
        "health": ["sick", "illness", "disease", "pain", "hurt", "injury", "disease", "doctor", "hospital", "medication"],
        "sleep": ["sleep", "insomnia", "sleepless", "tired", "fatigue", "exhausted", "cant sleep"],
        "anxiety": ["anxiety", "anxious", "nervous", "worry", "stressed", "panic", "overwhelm"],
        "depression": ["depressed", "depression", "sad", "hopeless", "empty", "numb", "meaningless"],
        "school": ["school", "college", "exam", "test", "grade", "study", "assignment", "university"],
        "finances": ["money", "financial", "broke", "debt", "expense", "bill", "rent", "mortgage"],
    }

    for category, keywords in stressor_keywords.items():
        if any(kw in combined_text for kw in keywords):
            facts[f"stressor_{category}"] = "mentioned"

    # Coping Strategies
    coping_keywords = {
        "exercise": ["exercise", "workout", "gym", "running", "walk", "yoga", "stretch"],
        "meditation": ["meditation", "mindful", "breathe", "breathing", "breath work"],
        "social_support": ["talk", "friend", "family", "support", "reach out", "call"],
        "creative": ["paint", "draw", "music", "write", "create", "art", "journal"],
        "sleep_routine": ["sleep", "bed", "rest", "nap", "bedtime"],
        "therapy": ["therapist", "therapy", "counselor", "counseling", "psychiatrist"],
    }

    for strategy, keywords in coping_keywords.items():
        if any(kw in combined_text for kw in keywords):
            facts[f"coping_{strategy}"] = "mentioned"

    # Mental Health Indicators
    if any(word in combined_text for word in ["suicide", "end it", "hurt myself", "self harm"]):
        facts["risk_indicator_crisis"] = "critical"

    if any(word in combined_text for word in ["depressed", "hopeless", "worthless", "no point"]):
        facts["mood_low"] = "true"

    if any(word in combined_text for word in ["excited", "happy", "great", "amazing", "wonderful"]):
        facts["mood_positive"] = "true"

    if any(word in combined_text for word in ["cant", "impossible", "never", "always fail"]):
        facts["thought_pattern_negative"] = "true"

    # Goals/Interests
    if any(word in combined_text for word in ["want", "goal", "plan", "hope", "dream", "wish"]):
        facts["has_goals"] = "true"

    # Previous Coping Success
    if any(phrase in combined_text for phrase in ["helped me", "worked before", "made me feel better", "got through"]):
        facts["has_previous_coping_success"] = "true"

    return facts


def _derive_session_analysis_from_rows(rows):
    """Derive tone/facts from stored chat_messages rows."""
    derived = {
        "tone": "neutral",
        "facts": {},
        "latest_user_input": "",
    }
    if not rows:
        return derived

    user_messages = []

    for row in rows:
        user_msg = row[0] if len(row) > 0 else ""

        if user_msg:
            user_text = str(user_msg).strip()
            if user_text:
                user_messages.append(user_text)
                derived["latest_user_input"] = user_text

    derived["tone"] = _infer_tone_from_user_messages(user_messages)
    # Extract facts from user messages
    derived["facts"] = _extract_facts_from_messages(user_messages)

    logger.info(f"Extracted facts from session: {list(derived['facts'].keys())}")

    return derived


def _build_assistant_summary_sentence(assistant_messages):
    """Build a concise sentence describing assistant behavior in session."""
    if not assistant_messages:
        return "The assistant responses were limited in this session."

    text = " ".join(assistant_messages).lower()
    parts = []
    if any(tok in text for tok in ("plan", "step", "routine", "schedule", "practice", "journal", "breathe", "sleep")):
        parts.append("practical coping guidance")
    if any(tok in text for tok in ("explain", "clarify", "means", "in simple terms", "break it down")):
        parts.append("clarification of the user's question")
    if any("?" in msg for msg in assistant_messages) or any(tok in text for tok in ("how", "what", "could you", "can you")):
        parts.append("follow-up questions for clarification")
    if any(tok in text for tok in ("i hear", "i understand", "that sounds", "you are feeling", "you seem")):
        parts.append("emotional validation")

    if parts:
        return f"The assistant provided {_join_phrases(parts)}."
    return "The assistant provided supportive responses to continue the discussion."


def _is_small_talk_message(text):
    """Heuristic for casual greeting/check-in messages."""
    msg = str(text or "").strip().lower()
    if not msg:
        return True
    greeting_markers = (
        "hi", "hello", "hey", "heyy", "hii", "yo", "sup", "good morning",
        "good evening", "good night", "how are you", "what about you",
        "all fine", "im fine", "i am fine", "ok", "okay", "cool", "thanks",
    )
    if msg in TRIVIAL_USER_INPUTS:
        return True
    return any(marker in msg for marker in greeting_markers)


def _build_session_discussion_summary(
    cur,
    user_id,
    session_id,
    fallback_summary="",
    latest_user_input="",
    risk_level="low",
    safety_action="none",
):
    """Create session-level summary from all chat turns for this session."""
    try:
        cur.execute(
            """
            SELECT
                user_message,
                assistant_response,
                final_reply_agent,
                memory_used
            FROM chat_messages
            WHERE user_id = %s AND session_id = %s
            ORDER BY user_msg_timestamp ASC
            """,
            (user_id, session_id),
        )
        rows = cur.fetchall()
    except Exception as e:
        logger.warning("Session summary rebuild failed: %s", e)
        return clean_summary(fallback_summary, latest_user_input)

    if not rows:
        return clean_summary(fallback_summary, latest_user_input)

    user_messages = [_summary_snippet(row[0], max_len=140) for row in rows if row and row[0]]
    user_messages = [msg for msg in user_messages if msg]
    assistant_messages = [_summary_snippet(row[1], max_len=140) for row in rows if row and row[1]]
    assistant_messages = [msg for msg in assistant_messages if msg]

    if not user_messages and not assistant_messages:
        return clean_summary(fallback_summary, latest_user_input)

    meaningful_msgs = [msg for msg in user_messages if not _is_trivial_input(msg)]
    latest_msg = user_messages[-1] if user_messages else _summary_snippet(latest_user_input, max_len=90) or "a brief check-in"
    total_turns = len(rows)
    user_text_blob = " ".join(user_messages).lower()

    small_talk_session = bool(user_messages) and all(_is_small_talk_message(msg) for msg in user_messages)
    clarification_intent = _contains_any(
        user_text_blob,
        ("what", "how", "why", "explain", "clarify", "what to do", "help me understand", "dont get", "don't get"),
    )

    # Old inferred-topic version kept for reference:
    # if meaningful_msgs and not (small_talk_session and total_turns <= 3):
    #     inferred_topics = _infer_user_topics(meaningful_msgs)
    #     if inferred_topics:
    #         verb = "asked for help with" if clarification_intent else "discussed"
    #         user_sentence = f"The user {verb} {_join_phrases(inferred_topics)}."
    #     else:
    #         discussion_points = _collect_unique_points(meaningful_msgs, max_points=2, max_len=90)
    #         if discussion_points:
    #             if total_turns <= 3:
    #                 user_sentence = "The user shared brief updates and asked for quick feedback."
    #             else:
    #                 if clarification_intent:
    #                     user_sentence = "The user asked for clarification about the current concern."
    #                 else:
    #                     user_sentence = f"The user mainly discussed {discussion_points[0]}."
    #                 if len(discussion_points) > 1:
    #                     user_sentence += f" They also referenced {discussion_points[1]}."
    #         else:
    #             user_sentence = "The user discussed a personal concern in this session."
    #     if _is_trivial_input(latest_msg):
    #         user_sentence += " The session ended with a brief check-in."
    # else:
    #     user_sentence = "The conversation was a brief check-in with casual messages and no detailed concern."

    if meaningful_msgs and not (small_talk_session and total_turns <= 3):
        discussion_points = _collect_unique_points(meaningful_msgs, max_points=2, max_len=90)
        if discussion_points:
            if total_turns <= 3:
                user_sentence = "The user shared brief updates and asked for quick feedback."
            else:
                if clarification_intent:
                    user_sentence = "The user asked for clarification about the current concern."
                else:
                    user_sentence = f"The user mainly discussed {discussion_points[0]}."
                if len(discussion_points) > 1:
                    user_sentence += f" They also referenced {discussion_points[1]}."
        else:
            user_sentence = "The user discussed a personal concern in this session."
        if _is_trivial_input(latest_msg):
            user_sentence += " The session ended with a brief check-in."
    else:
        user_sentence = "The conversation was a brief check-in with casual messages and no detailed concern."

    assistant_sentence = _build_assistant_summary_sentence(assistant_messages)
    reliability_sentence = ""
    if _assistant_had_connection_issue(assistant_messages):
        reliability_sentence = "One assistant reply appears to have been degraded by a connection issue."

    # Note: Legacy agent columns (agent_safety, agent_memory, agent_orchestrator) were removed
    # from the database schema. Now using memory_used and final_reply_agent from the new architecture.
    memory_active = any(_agent_was_active(row[3]) for row in rows if len(row) > 3)
    risk_norm = str(risk_level or "low").strip().lower()
    safety_norm = str(safety_action or "none").strip().lower()
    context_notes = []
    if risk_norm == "high":
        context_notes.append("High-risk support flow was activated during this conversation.")
    elif risk_norm == "medium" or "monitor" in safety_norm:
        context_notes.append("Safety monitoring was applied during this conversation.")
    if memory_active:
        context_notes.append("Prior-session context was used to maintain continuity.")

    outcome_sentence = _infer_session_outcome(user_messages)

    turn_label = "turn" if total_turns == 1 else "turns"
    context_notes.append(f"This session had {total_turns} {turn_label} between the user and the assistant.")

    session_summary = " ".join(
        part for part in [user_sentence, assistant_sentence, reliability_sentence, outcome_sentence] + context_notes if part
    )
    return clean_summary(session_summary, latest_user_input)




def _hash_password(password: str) -> str:
    """Returns a SHA-256 hex digest of the password. Use for storing/comparing passwords."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def register_user(user_data):
    """Registers a user with full demographics including role, email, and password."""
    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            email = user_data.get('email', '')
            raw_password = user_data.get('password', '')
            pw_hash = _hash_password(raw_password) if raw_password else ''
            query = """
            INSERT INTO users (username, full_name, dob, gender, role, country, state, city, pincode, mobile_number, email, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING user_id;
            """
            cur.execute(query, (
                user_data['username'], user_data['full_name'], user_data['dob'],
                user_data['gender'], user_data.get('role', 'Patient'), user_data['country'], user_data['state'],
                user_data['city'], user_data['pincode'], user_data['mobile'],
                email, pw_hash
            ))
            result = cur.fetchone()
            if not result:
                logger.error("Registration: Failed to get user_id from RETURNING clause")
                conn.rollback()
                return None
            u_id = result[0]
            conn.commit()
            return u_id
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return "EXISTS"
        except Exception as e:
            conn.rollback()
            logger.error("Registration Error: %s", e)
            st.error(f"Registration Error: {e}")
            return None
        finally:
            cur.close()


def verify_user_login(mobile):
    """Returns essential user info for session state."""
    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT user_id, full_name, username FROM users WHERE mobile_number = %s", (mobile,))
            return cur.fetchone()
        finally:
            cur.close()


def verify_user_email_password(email: str, password: str):
    """Verify login via email + password. Returns (user_id, full_name, username) or None."""
    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            pw_hash = _hash_password(password)
            cur.execute(
                "SELECT user_id, full_name, username FROM users WHERE email = %s AND password_hash = %s",
                (email.strip().lower(), pw_hash),
            )
            return cur.fetchone()
        except Exception as e:
            logger.error("verify_user_email_password error: %s", e)
            return None
        finally:
            cur.close()


def update_verification(user_id):
    """Finalizes user setup. (#38 — wrapped in try/except)"""
    with get_pooled_connection() as conn:
        if not conn:
            return False
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET is_verified = TRUE WHERE user_id = %s", (user_id,))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"update_verification failed: {e}")
            return False
        finally:
            cur.close()


def save_onboarding(user_id, questions, answers):
    """Saves onboarding question-answer pairs. Role is set during signup, not here."""
    with get_pooled_connection() as conn:
        if not conn:
            return False
        cur = conn.cursor()
        try:
            current_time = datetime.now()
            for i, (q, a) in enumerate(zip(questions, answers)):
                row_time = current_time + timedelta(milliseconds=i * 10)
                cur.execute(
                    "INSERT INTO onboarding_que (user_id, question, answer, created_at) VALUES (%s, %s, %s, %s)",
                    (user_id, q, a, row_time),
                )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            st.error(f"Onboarding Save Error: {e}")
            return False
        finally:
            cur.close()


def fetch_onboarding_answers(user_id):
    """Fetch onboarding question-answer pairs for personalization (#28)."""
    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT question, answer FROM onboarding_que WHERE user_id = %s ORDER BY created_at ASC",
                (user_id,),
            )
            rows = cur.fetchall()
            return [{"question": q, "answer": a} for q, a in rows]
        except Exception as e:
            logger.error(f"fetch_onboarding_answers error: {e}")
            return []
        finally:
            cur.close()

#### changes by SB starts #########
# def save_chat_message(user_id, session_id, user_msg, assistant_msg, user_time, bot_time, agent_safety="No", agent_memory="No", agent_orchestrator="No", agent_coach="No", latency=0.0): #PRoblem 
#     """Logs chat with latency tracking and raw per-agent outputs."""
#     session_id_norm = _coerce_session_id(session_id)
#     if not session_id_norm:
#         logger.error("save_chat_message skipped: invalid session_id=%s", session_id)
#         return False

#     with get_pooled_connection() as conn:
#         if not conn:
#             return False
#         cur = conn.cursor()
#         try:
#             # Store actual agent outputs (not just Yes/No), with sane caps.
#             safety_payload = (agent_safety or "").strip()
#             memory_payload = (agent_memory or "").strip()
#             orchestrator_payload = (agent_orchestrator or "").strip()
#             coach_payload = (agent_coach or "").strip()
#             if len(safety_payload) > 3000:
#                 safety_payload = safety_payload[:3000]
#             if len(memory_payload) > 3000:
#                 memory_payload = memory_payload[:3000]
#             if len(orchestrator_payload) > 3000:
#                 orchestrator_payload = orchestrator_payload[:3000]
#             if len(coach_payload) > 3000:
#                 coach_payload = coach_payload[:3000]

#             cur.execute(
#                 """INSERT INTO chat_messages
#                    (user_id, session_id, user_message, assistant_response,
#                     user_msg_timestamp, bot_msg_timestamp, latency_seconds,
#                     agent_safety, agent_memory, agent_orchestrator, agent_coach)
#                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
#                 (user_id, session_id_norm, user_msg, assistant_msg, user_time, bot_time, latency,
#                  safety_payload, memory_payload, orchestrator_payload, coach_payload),
#             )
#             conn.commit()
#             return True
#         except Exception as e:
#             conn.rollback()
#             logger.error(f"save_chat_message Error: {e}")
#             return False
#         finally:
#             cur.close()

def save_chat_message(
    user_id,
    session_id,
    user_msg,
    assistant_msg,
    user_time,
    bot_time,
    latency=0.0,
    risk_level="low",
    safety_action="normal",
    intent_label="general_support",
    response_mode="supportive",
    memory_used=False,
    memory_type="",
    escalation_flag=False,
    final_reply_agent="coach",
    fallback_triggered=False,
    rag_used=False,
    doc_id=None,  # List of doc_ids from top-3 RAG chunks
    rag_source=None,  # Where context came from (memory, onboarding, past_chat, etc.)
    retrieved_count=None,  # How many chunks/items were fetched
    retrieval_score=None,  # Top score or average score
    grounded_flag=False,  # Whether final answer actually used retrieved context
    rag_benefit_flag=False,  # Did retrieval help this response
):
    """Logs chat with both legacy fields and new locked-architecture fields.

    Implements automatic retry on deadlock (up to 3 attempts) since deadlocks
    are transient and safe to retry in this context.
    """
    import time

    session_id_norm = _coerce_session_id(session_id)
    if not session_id_norm:
        logger.error("save_chat_message skipped: invalid session_id=%s", session_id)
        return False

    # Get next message_id from sequence BEFORE retry loop (only call once!)
    with get_pooled_connection() as conn_seq:
        if not conn_seq:
            return False
        cur_seq = conn_seq.cursor()
        try:
            cur_seq.execute("SELECT nextval('chat_messages_message_id_seq')")
            next_message_id = cur_seq.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to get next message_id: {e}")
            return False

    max_retries = 3
    for attempt in range(max_retries):
        with get_pooled_connection() as conn:
            if not conn:
                return False
            cur = conn.cursor()
            try:
                # Normalize fields
                normalized_memory_type = memory_type if memory_type and memory_type.strip() else "-"
                normalized_risk = _normalize_risk(risk_level)
                normalized_safety_action = (safety_action or "normal").strip().lower()
                normalized_intent = (intent_label or "general_support").strip()
                normalized_mode = (response_mode or "supportive").strip()
                normalized_final_agent = (final_reply_agent or "coach").strip().lower()

                # Acquire advisory lock to ensure sequential serial_no (no gaps)
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('chat_messages_serial_no'))")

                # Calculate next serial_no manually to ensure no gaps
                cur.execute("SELECT COALESCE(MAX(serial_no), 0) + 1 FROM chat_messages")
                next_serial_no = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO chat_messages
                    (
                        message_id, serial_no,
                        user_id, session_id,
                        user_message, assistant_response,
                        user_msg_timestamp, bot_msg_timestamp, latency_seconds,
                        risk_level, safety_action,
                        intent_label, response_mode, memory_used, memory_type,
                        escalation_flag, final_reply_agent, fallback_triggered,
                        rag_used, doc_id,
                        rag_source, retrieved_count, retrieval_score, grounded_flag, rag_benefit_flag
                    )
                    VALUES
                    (
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s::integer[],
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        next_message_id, next_serial_no,
                        user_id, session_id_norm,
                        user_msg, assistant_msg,
                        user_time, bot_time, latency,
                        normalized_risk, normalized_safety_action,
                        normalized_intent, normalized_mode, bool(memory_used), normalized_memory_type,
                        bool(escalation_flag), normalized_final_agent, bool(fallback_triggered),
                        bool(rag_used), doc_id,
                        rag_source, retrieved_count, retrieval_score, bool(grounded_flag), bool(rag_benefit_flag),
                    ),
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                # Check if it's a deadlock error (PostgreSQL error code 40P01)
                if "deadlock" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)  # Exponential backoff: 0.1s, 0.2s, 0.4s
                    logger.warning(f"Deadlock on attempt {attempt + 1}/{max_retries}, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                logger.error(f"save_chat_message Error: {e}")
                return False
            finally:
                cur.close()

##### changes by SB ends #########


def load_specific_session(user_id, session_id):
    """Rebuilds the chat history list for the UI from a specific session ID."""
    session_id_norm = _coerce_session_id(session_id)
    if not session_id_norm:
        logger.warning("load_specific_session skipped: invalid session_id=%s", session_id)
        return []

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT user_message, assistant_response
                FROM chat_messages
                WHERE user_id = %s AND session_id = %s
                ORDER BY user_msg_timestamp ASC
            """, (user_id, session_id_norm))
            rows = cur.fetchall()
            formatted_messages = []
            for row in rows:
                formatted_messages.append({"role": "user", "content": row[0]})
                formatted_messages.append({"role": "assistant", "content": row[1]})
            return formatted_messages
        except Exception as e:
            logger.error(f"Session Load Error: {e}")
            return []
        finally:
            cur.close()


def fetch_all_session_summaries(user_id, limit=50, search_keywords=None, exclude_session_id=None, _cur=None):
    """Fetch past session summaries with tones and facts for cross-session memory.

    Accepts an optional cursor `_cur` so it can be called inside a shared connection.
    Excludes the current session_id if provided (to ensure only PREVIOUS sessions are returned).
    """
    def _run(cur):
        # custom changes start
        # Include sessions where session_summary is populated but summary_text isn't yet
        # (happens when user closes app before inactivity finalizer runs).
        where_clause = "WHERE user_id = %s AND (summary_text IS NOT NULL OR session_summary IS NOT NULL)"
        params = [user_id]

        # CRITICAL FIX: Exclude current session so previous_sessions doesn't include it
        if exclude_session_id:
            where_clause += " AND session_id != %s"
            params.append(_coerce_session_id(exclude_session_id))
        if search_keywords:
            like_patterns = [f"%{k}%" for k in search_keywords if k]
            if like_patterns:
                where_clause += " AND (summary_text ILIKE ANY(%s) OR session_summary ILIKE ANY(%s))"
                params.append(like_patterns)
                params.append(like_patterns)

        query = f"""
            SELECT
                COALESCE(summary_text, session_summary) AS summary_text,
                detected_tone,
                user_facts_json,
                COALESCE(last_updated, created_at) AS updated_at,
                session_id
            FROM chat_analysis
            {where_clause}
            ORDER BY COALESCE(last_updated, created_at) DESC
            LIMIT %s
        """
        # custom changes end
        params.append(limit)
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        sessions = []
        for row in rows:
            summary, tone, facts_raw, updated_at, session_id = row
            facts = _coerce_facts_payload(facts_raw)
            date_str = updated_at.strftime("%b %d, %Y") if updated_at else "Unknown"
            sessions.append({
                "summary": summary or "General conversation",
                "tone": tone or "neutral",
                "facts": facts,
                "date": date_str,
                "session_id": str(session_id) if session_id else "",
            })
        return sessions

    if _cur is not None:
        return _run(_cur)

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            return _run(cur)
        except Exception as e:
            logger.error(f"fetch_all_session_summaries error: {e}")
            return []
        finally:
            cur.close()


def _record_fact_conflict(base, key, old_value, new_value):
    """Track conflicting fact values for auditability."""
    conflicts = base.setdefault("_fact_conflicts", {})
    entry = conflicts.setdefault(key, [])
    old_s = str(old_value)
    new_s = str(new_value)
    if old_s not in entry:
        entry.append(old_s)
    if new_s not in entry:
        entry.append(new_s)


def _deep_merge_facts(base, new):
    """Merge new facts into base, retain conflict history, and cap accumulation."""
    for key, value in new.items():
        if key == "_fact_conflicts":
            continue
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge_facts(base[key], value)
        elif key in base and str(base[key]) != str(value):
            _record_fact_conflict(base, key, base[key], value)
            base[key] = value
        else:
            base[key] = value
    # P1#5: Cap fact conflicts to last 5 entries per key
    conflicts = base.get("_fact_conflicts", {})
    for ckey in list(conflicts.keys()):
        if isinstance(conflicts[ckey], list) and len(conflicts[ckey]) > 5:
            conflicts[ckey] = conflicts[ckey][-5:]
    # Cap total top-level fact keys to 100 (keep most recent)
    skip_keys = {"_fact_conflicts", "topic_state", "preferences"}
    removable = [k for k in base if k not in skip_keys]
    if len(removable) > 100:
        for old_key in removable[:len(removable) - 100]:
            del base[old_key]

# def fetch_master_memory(user_id, search_text=None, _cur=None):
#     """Temporary safe version: do not use chat_analysis for retrieval."""
#     return {
#         "summary": "First conversation.",
#         "facts": {},
#         "last_tone": "neutral",
#         "last_risk": "low",
#         "mood_history": [],
#         "session_history": [],
#         "has_history": False,
#     }

def fetch_master_memory(user_id, search_text=None, _cur=None):
    """Retrieves complete user profile including cross-session history and behavioral patterns.

    Accepts optional cursor for use inside a shared connection.
    """
    empty = {"summary": "First conversation.", "facts": {}, "last_tone": "neutral", "last_risk": "low", "mood_history": [], "session_history": []}

    def _run(cur):
        # Get the main analysis profile (latest session)
        cur.execute(
            """
            SELECT last_risk_level, detected_tone, user_facts_json, summary_text
            FROM chat_analysis
            WHERE user_id = %s
            ORDER BY COALESCE(last_updated, created_at) DESC
            LIMIT 1
            """,
            (user_id,),
        )
        result = cur.fetchone()

        # Recent mood/tone history — fetch actual tone data (#44)
        cur.execute("""
            SELECT ca.detected_tone, cm.user_msg_timestamp
            FROM chat_messages cm
            LEFT JOIN chat_analysis ca ON cm.user_id = ca.user_id AND cm.session_id = ca.session_id
            WHERE cm.user_id = %s
            ORDER BY cm.user_msg_timestamp DESC
            LIMIT 5
        """, (user_id,))
        mood_rows = cur.fetchall()
        mood_history = []
        for tone, timestamp in mood_rows:
            if timestamp:
                label = f"{timestamp.strftime('%b %d')}"
                if tone:
                    label += f" ({tone})"
                mood_history.append(label)

        # Cross-session summaries — relevance-aware fetch with capped window
        search_keywords = _extract_search_keywords(search_text) if search_text else []
        session_history = fetch_all_session_summaries(
            user_id, limit=20, search_keywords=search_keywords, _cur=cur
        )
        if len(session_history) < 10 and search_keywords:
            # Backfill with recency if keyword filtering was too narrow.
            recent_history = fetch_all_session_summaries(user_id, limit=15, _cur=cur)
            seen = {s.get("session_id") for s in session_history}
            for sess in recent_history:
                sid = sess.get("session_id")
                if sid in seen:
                    continue
                session_history.append(sess)
                seen.add(sid)
                if len(session_history) >= 25:
                    break

        # Deep-merge facts (#29)
        all_facts = {}
        for session in reversed(session_history):
            if session.get("facts"):
                _deep_merge_facts(all_facts, session["facts"])

        if result:
            if result[2]:
                try:
                    latest_facts = _coerce_facts_payload(result[2])
                    _deep_merge_facts(all_facts, latest_facts)
                except Exception as e:
                    logger.warning(f"Failed to parse latest facts: {e}")

            latest_summary = (result[3] or "").strip()
            if not _is_high_information_summary(latest_summary):
                for sess in session_history:
                    candidate = (sess.get("summary") or "").strip()
                    if _is_high_information_summary(candidate):
                        latest_summary = candidate
                        break
            if not latest_summary:
                latest_summary = "Continuing our conversation."

            return {
                "summary": latest_summary,
                "facts": all_facts,
                "last_tone": result[1] or "neutral",
                "last_risk": result[0] or "low",
                "mood_history": mood_history,
                "session_history": session_history,
                "has_history": True,
            }
        return {"summary": "First conversation.", "facts": all_facts, "last_tone": "neutral", "last_risk": "low", "mood_history": [], "session_history": session_history, "has_history": len(session_history) > 0}

    if _cur is not None:
        return _run(_cur)

    with get_pooled_connection() as conn:
        if not conn:
            return empty
        cur = conn.cursor()
        try:
            return _run(cur)
        finally:
            cur.close()


def fetch_recent_messages(user_id, session_id=None, limit=30, _cur=None):
    """Get recent conversation messages across ALL sessions for full context.

    Fixes: removed ::text cast (#33), added dedup (#34), accepts shared cursor.
    """
    def _run(cur):
        if session_id:
            cur.execute(
                """
                SELECT
                    cm.user_message,
                    cm.assistant_response,
                    cm.user_msg_timestamp,
                    cm.session_id
                FROM chat_messages cm
                WHERE cm.user_id = %s AND cm.session_id = %s
                ORDER BY cm.user_msg_timestamp DESC
                LIMIT %s
                """,
                (user_id, session_id, limit),
            )
        else:
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        cm.user_message,
                        cm.assistant_response,
                        cm.user_msg_timestamp,
                        cm.session_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY cm.session_id
                            ORDER BY cm.user_msg_timestamp DESC
                        ) AS rn
                    FROM chat_messages cm
                    WHERE cm.user_id = %s
                )
                SELECT user_message, assistant_response, user_msg_timestamp, session_id
                FROM ranked
                WHERE rn <= 5
                ORDER BY user_msg_timestamp DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
        rows = cur.fetchall()

        messages = []
        prev_session = None
        seen_user = set()
        for row in reversed(rows):
            user_msg, bot_msg, timestamp, sess_id = row
            msg_key = (user_msg or "")[:50].strip().lower()
            if msg_key and msg_key in seen_user:
                continue
            if msg_key:
                seen_user.add(msg_key)
            time_str = timestamp.strftime("%b %d") if timestamp else ""
            if sess_id and str(sess_id) != str(prev_session) and prev_session is not None:
                messages.append(f"--- [New session on {time_str}] ---")
            prev_session = sess_id
            messages.append(f"[{time_str}] User: {user_msg}")
            assistant_text = " ".join(str(bot_msg or "").split())
            messages.append(f"[{time_str}] Assistant: {assistant_text}")
        return messages

    if _cur is not None:
        return _run(_cur)

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            return _run(cur)
        except Exception as e:
            logger.error(f"fetch_recent_messages error: {e}")
            return []
        finally:
            cur.close()


def analyze_mood_patterns(user_id, days=7, _cur=None):
    """Analyze user's mood/stress patterns over the past N days.

    Fixes: removed ::text cast (#33), accepts shared cursor.
    """
    def _run(cur):
        cur.execute("""
            SELECT
                cm.user_message,
                cm.user_msg_timestamp::date as msg_date
            FROM chat_messages cm
            WHERE cm.user_id = %s
            AND cm.user_msg_timestamp >= CURRENT_DATE - (%s * INTERVAL '1 day')
            ORDER BY cm.user_msg_timestamp DESC
            LIMIT 20
        """, (user_id, days))
        rows = cur.fetchall()

        if not rows or len(rows) < 2:
            return None

        negative_tones = [
            'stressed', 'anxious', 'sad', 'frustrated',
            'worried', 'tired', 'exhausted', 'lonely', 'angry', 'hopeless',
            'tense', 'nervous', 'upset', 'down', 'low',
        ]
        negative_messages = []
        stress_keywords = {}
        risk_days = []
        severe_markers = (
            "hopeless", "worthless", "panic", "can't go on", "cant go on",
            "breaking down", "falling apart", "giving up", "hate myself",
        )

        for row in rows:
            user_msg, msg_date = row
            user_text = str(user_msg or "").strip()
            if not user_text:
                continue

            tone = _infer_tone_from_user_messages([user_text])
            tone_lower = tone.lower()
            text_lower = user_text.lower()
            is_negative = any(neg in tone_lower for neg in negative_tones) or any(tok in text_lower for tok in severe_markers)
            if is_negative:
                negative_messages.append({'message': user_text[:100], 'tone': tone, 'date': msg_date})
                for word in ['work', 'job', 'exam', 'study', 'family', 'relationship',
                             'money', 'health', 'sleep', 'boss', 'deadline', 'pressure']:
                    if word in text_lower:
                        stress_keywords[word] = stress_keywords.get(word, 0) + 1
                risk_days.append(msg_date)

        if len(negative_messages) < 2:
            return None

        recurring_topics = [k for k, v in stress_keywords.items() if v >= 2]
        pattern_data = {
            'has_patterns': True,
            'negative_count': len(negative_messages),
            'recurring_topics': recurring_topics,
            'recent_negative_tone': negative_messages[0]['tone'] if negative_messages else None,
            'days_with_stress': len(set(risk_days)),
        }
        if recurring_topics:
            pattern_data['pattern_hint'] = (
                f"User has mentioned feeling stressed about {', '.join(recurring_topics)} "
                f"multiple times in the past week."
            )
        elif len(negative_messages) >= 3:
            pattern_data['pattern_hint'] = (
                f"User has been going through a tough time - {len(negative_messages)} "
                f"messages with negative emotions in the past week."
            )
        return pattern_data

    if _cur is not None:
        return _run(_cur)

    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            return _run(cur)
        except Exception as e:
            logger.error(f"analyze_mood_patterns error: {e}")
            return None
        finally:
            cur.close()

##### changes by SB starts #########
# def update_master_analysis(
#     user_id,
#     session_id,
#     risk,
#     safety,
#     tone,
#     facts,
#     summary,
#     user_input="",
#     reply_source="orchestrator",
#     finalize_summary=False,
# ):
#     """Updates session analysis data.

#     When finalize_summary is False, only metadata (risk/safety/tone/facts/source)
#     is updated and summary_text is kept unchanged.
#     When True, summary_text is rebuilt from the full session transcript.
#     """
#     session_id_norm = _coerce_session_id(session_id)
#     if not session_id_norm:
#         logger.error("update_master_analysis skipped: invalid session_id=%s", session_id)
#         return False

#     with get_pooled_connection() as conn:
#         if not conn:
#             return False
#         cur = conn.cursor()
#         try:
#             # Serialize writes per (user_id, session_id) to avoid duplicate inserts.
#             cur.execute(
#                 "SELECT pg_advisory_xact_lock(hashtext(%s))",
#                 (f"chat_analysis:{user_id}:{session_id_norm}",),
#             )
#             cur.execute(
#                 """
#                 SELECT visible_serial_no, user_facts_json, summary_text
#                 FROM chat_analysis
#                 WHERE user_id = %s AND session_id = %s
#                 ORDER BY COALESCE(last_updated, created_at) DESC, visible_serial_no DESC
#                 """,
#                 (user_id, session_id_norm),
#             )
#             existing_rows = cur.fetchall()
#             existing_row = existing_rows[0] if existing_rows else None

#             if len(existing_rows) > 1:
#                 dup_serials = [row[0] for row in existing_rows[1:] if row and row[0] is not None]
#                 if dup_serials:
#                     cur.execute(
#                         """
#                         DELETE FROM chat_analysis
#                         WHERE user_id = %s AND session_id = %s
#                           AND visible_serial_no = ANY(%s)
#                         """,
#                         (user_id, session_id_norm, dup_serials),
#                     )
#                     logger.warning(
#                         "Deduplicated chat_analysis rows for user=%s session=%s removed=%d",
#                         user_id, session_id_norm, len(dup_serials)
#                     )

#             existing_facts = {}
#             existing_summary = ""
#             if existing_row and existing_row[1]:
#                 try:
#                     existing_facts = _coerce_facts_payload(existing_row[1])
#                 except Exception as e:
#                     logger.warning(f"Failed to parse existing facts: {e}")
#                     existing_facts = {}
#             if existing_row and existing_row[2]:
#                 existing_summary = str(existing_row[2]).strip()

#             cleaned_facts = clean_facts(facts, existing_facts)
#             cleaned_summary = None
#             if finalize_summary:
#                 cleaned_summary = _build_session_discussion_summary(
#                     cur,
#                     user_id,
#                     session_id_norm,
#                     fallback_summary=summary,
#                     latest_user_input=user_input,
#                     risk_level=risk,
#                     safety_action=safety,
#                 )
#                 if not cleaned_summary:
#                     cleaned_summary = clean_summary(summary, user_input)
#                 if not cleaned_summary and existing_summary:
#                     cleaned_summary = existing_summary
#                 if not cleaned_summary:
#                     cleaned_summary = "General conversation."
#             else:
#                 # Keep summary blank/unchanged during active session.
#                 # Final summary is generated only during inactivity finalization.
#                 cleaned_summary = existing_summary or None

#             merged_facts = {}
#             _deep_merge_facts(merged_facts, existing_facts or {})
#             _deep_merge_facts(merged_facts, cleaned_facts or {})

#             if existing_row:
#                 cur.execute(
#                     """UPDATE chat_analysis SET
#                         last_risk_level = %s, safety_action_taken = %s, detected_tone = %s,
#                         user_facts_json = %s, summary_text = %s, reply_agent_source = %s, last_updated = %s
#                     WHERE user_id = %s AND session_id = %s""",
#                     (risk, safety, tone, json.dumps(merged_facts), cleaned_summary, reply_source, datetime.now(), user_id, session_id_norm),
#                 )
#             else:
#                 # Global serial sequence across all chat_analysis rows.
#                 cur.execute("SELECT pg_advisory_xact_lock(hashtext('chat_analysis_visible_serial_global'))")
#                 cur.execute("SELECT COALESCE(MAX(visible_serial_no), 0) + 1 FROM chat_analysis")
#                 next_serial = cur.fetchone()[0]
#                 now = datetime.now()
#                 insert_params = (
#                     next_serial, user_id, session_id_norm, risk, safety, tone,
#                     json.dumps(merged_facts), cleaned_summary, reply_source, now, now
#                 )
#                 try:
#                     cur.execute(
#                         """INSERT INTO chat_analysis (
#                             visible_serial_no, user_id, session_id, last_risk_level,
#                             safety_action_taken, detected_tone, user_facts_json, summary_text,
#                             reply_agent_source, created_at, last_updated
#                         ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                         ON CONFLICT (user_id, session_id) DO UPDATE SET
#                             last_risk_level = EXCLUDED.last_risk_level,
#                             safety_action_taken = EXCLUDED.safety_action_taken,
#                             detected_tone = EXCLUDED.detected_tone,
#                             user_facts_json = EXCLUDED.user_facts_json,
#                             summary_text = EXCLUDED.summary_text,
#                             reply_agent_source = EXCLUDED.reply_agent_source,
#                             last_updated = EXCLUDED.last_updated
#                         """,
#                         insert_params,
#                     )
#                 except Exception as upsert_err:
#                     msg = str(upsert_err).lower()
#                     if "no unique or exclusion constraint matching the on conflict specification" not in msg:
#                         raise
#                     cur.execute(
#                         """INSERT INTO chat_analysis (
#                             visible_serial_no, user_id, session_id, last_risk_level,
#                             safety_action_taken, detected_tone, user_facts_json, summary_text,
#                             reply_agent_source, created_at, last_updated
#                         ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
#                         insert_params,
#                     )

#             conn.commit()
#             return True
#         except Exception as e:
#             conn.rollback()
#             logger.error(f"Analysis Update Error: {e}")
#             return False
#         finally:
#             cur.close()

def update_master_analysis(
    user_id,
    session_id,
    risk,
    safety,
    tone,
    facts,
    summary,
    user_input="",
    reply_source="coach",
    finalize_summary=False,
    dominant_emotion=None,
    repeated_stressors=None,
    risk_trend=None,
    escalation_flag=False,
    recommended_followup=None,
):
    """
    Transitional analysis writer:
    - preserves legacy columns
    - also writes new locked-architecture columns
    """
    session_id_norm = _coerce_session_id(session_id)
    if not session_id_norm:
        logger.error("update_master_analysis skipped: invalid session_id=%s", session_id)
        return False

    with get_pooled_connection() as conn:
        if not conn:
            return False
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"chat_analysis:{user_id}:{session_id_norm}",),
            )

            cur.execute(
                """
                SELECT serial_no, user_facts_json, summary_text
                FROM chat_analysis
                WHERE user_id = %s AND session_id = %s
                ORDER BY COALESCE(last_updated, created_at) DESC, serial_no DESC
                """,
                (user_id, session_id_norm),
            )
            existing_rows = cur.fetchall()
            existing_row = existing_rows[0] if existing_rows else None

            if len(existing_rows) > 1:
                dup_serials = [row[0] for row in existing_rows[1:] if row and row[0] is not None]
                if dup_serials:
                    cur.execute(
                        """
                        DELETE FROM chat_analysis
                        WHERE user_id = %s AND session_id = %s
                          AND serial_no = ANY(%s)
                        """,
                        (user_id, session_id_norm, dup_serials),
                    )

            existing_facts = {}
            existing_summary = ""
            if existing_row and existing_row[1]:
                try:
                    existing_facts = _coerce_facts_payload(existing_row[1])
                except Exception:
                    existing_facts = {}
            if existing_row and existing_row[2]:
                existing_summary = str(existing_row[2]).strip()

            cleaned_facts = clean_facts(facts, existing_facts)

            if finalize_summary:
                cleaned_summary = _build_session_discussion_summary(
                    cur,
                    user_id,
                    session_id_norm,
                    fallback_summary=summary,
                    latest_user_input=user_input,
                    risk_level=risk,
                    safety_action=safety,
                )
                if not cleaned_summary:
                    cleaned_summary = clean_summary(summary, user_input)
                if not cleaned_summary and existing_summary:
                    cleaned_summary = existing_summary
                if not cleaned_summary:
                    cleaned_summary = "General conversation."
            else:
                cleaned_summary = existing_summary or None

            merged_facts = {}
            _deep_merge_facts(merged_facts, existing_facts or {})
            _deep_merge_facts(merged_facts, cleaned_facts or {})

            # New architecture fields
            normalized_session_summary = cleaned_summary
            normalized_dominant_emotion = dominant_emotion or tone or "neutral"
            normalized_repeated_stressors = repeated_stressors or ""
            normalized_risk_trend = risk_trend or _normalize_risk(risk)
            normalized_escalation_flag = bool(escalation_flag)
            normalized_recommended_followup = recommended_followup or ""

            if existing_row:
                cur.execute(
                    """
                    UPDATE chat_analysis SET
                        last_risk_level = %s,
                        safety_action_taken = %s,
                        detected_tone = %s,
                        user_facts_json = %s,
                        summary_text = %s,
                        reply_agent_source = %s,
                        last_updated = %s,

                        session_summary = %s,
                        dominant_emotion = %s,
                        repeated_stressors = %s,
                        risk_trend = %s,
                        escalation_flag = %s,
                        recommended_followup = %s
                    WHERE user_id = %s AND session_id = %s
                    """,
                    (
                        risk, safety, tone, json.dumps(merged_facts), cleaned_summary, reply_source, datetime.now(),
                        normalized_session_summary, normalized_dominant_emotion,
                        normalized_repeated_stressors, normalized_risk_trend,
                        normalized_escalation_flag, normalized_recommended_followup,
                        user_id, session_id_norm,
                    ),
                )
            else:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('chat_analysis_serial_no_global'))")
                cur.execute("SELECT COALESCE(MAX(serial_no), 0) + 1 FROM chat_analysis")
                result = cur.fetchone()
                if not result:
                    logger.error(f"Failed to get next serial: fetchone returned None for user {user_id}")
                    return False
                next_serial = result[0]
                now = datetime.now()

                insert_params = (
                    next_serial, user_id, session_id_norm,
                    risk, safety, tone, json.dumps(merged_facts), cleaned_summary, reply_source, now, now,
                    normalized_session_summary, normalized_dominant_emotion,
                    normalized_repeated_stressors, normalized_risk_trend,
                    normalized_escalation_flag, normalized_recommended_followup,
                )

                try:
                    cur.execute(
                        """
                        INSERT INTO chat_analysis (
                            serial_no, user_id, session_id,
                            last_risk_level, safety_action_taken, detected_tone,
                            user_facts_json, summary_text, reply_agent_source,
                            created_at, last_updated,

                            session_summary, dominant_emotion, repeated_stressors,
                            risk_trend, escalation_flag, recommended_followup
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, session_id) DO UPDATE SET
                            last_risk_level = EXCLUDED.last_risk_level,
                            safety_action_taken = EXCLUDED.safety_action_taken,
                            detected_tone = EXCLUDED.detected_tone,
                            user_facts_json = EXCLUDED.user_facts_json,
                            summary_text = EXCLUDED.summary_text,
                            reply_agent_source = EXCLUDED.reply_agent_source,
                            last_updated = EXCLUDED.last_updated,

                            session_summary = EXCLUDED.session_summary,
                            dominant_emotion = EXCLUDED.dominant_emotion,
                            repeated_stressors = EXCLUDED.repeated_stressors,
                            risk_trend = EXCLUDED.risk_trend,
                            escalation_flag = EXCLUDED.escalation_flag,
                            recommended_followup = EXCLUDED.recommended_followup
                        """,
                        insert_params,
                    )
                except Exception as upsert_err:
                    msg = str(upsert_err).lower()
                    if "no unique or exclusion constraint matching the on conflict specification" not in msg:
                        raise
                    # The failed statement above aborted the transaction — Postgres will
                    # reject any further command on this connection until we roll back.
                    conn.rollback()
                    cur.execute(
                        """
                        INSERT INTO chat_analysis (
                            serial_no, user_id, session_id,
                            last_risk_level, safety_action_taken, detected_tone,
                            user_facts_json, summary_text, reply_agent_source,
                            created_at, last_updated,

                            session_summary, dominant_emotion, repeated_stressors,
                            risk_trend, escalation_flag, recommended_followup
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        insert_params,
                    )

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            import traceback
            logger.error(f"Analysis Update Error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            cur.close()

#### changes by SB ends #########


def get_session_last_activity(user_id, session_id):
    """Return the latest activity timestamp for a specific session."""
    session_id_norm = _coerce_session_id(session_id)
    if not session_id_norm:
        logger.warning("get_session_last_activity skipped: invalid session_id=%s", session_id)
        return None

    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT MAX(COALESCE(bot_msg_timestamp, user_msg_timestamp))
                FROM chat_messages
                WHERE user_id = %s AND session_id = %s
                """,
                (user_id, session_id_norm),
            )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning("get_session_last_activity failed: %s", e)
            return None
        finally:
            cur.close()


def finalize_session_analysis(user_id, session_id):
    """Finalize session summary from full transcript after inactivity cutoff."""
    session_id_norm = _coerce_session_id(session_id)
    if not session_id_norm:
        logger.error("finalize_session_analysis skipped: invalid session_id=%s", session_id)
        return False

    # Acquire a per-session threading lock before doing any DB work.
    # This prevents two concurrent Streamlit reruns from finalizing the same session
    # simultaneously — which is the root cause of the deadlock (both transactions
    # read chat_analysis then chat_messages but a concurrent save_chat_message /
    # update_master_analysis holds chat_messages in the opposite order, creating a cycle).
    lock_key = f"{user_id}:{session_id_norm}"
    with _finalize_session_locks_guard:
        if lock_key not in _finalize_session_locks:
            _finalize_session_locks[lock_key] = threading.Lock()
        session_lock = _finalize_session_locks[lock_key]

    acquired = session_lock.acquire(blocking=False)
    if not acquired:
        # Another thread is already finalizing this exact session — skip gracefully.
        logger.info("finalize_session_analysis skipped: already in progress for session %s", session_id_norm)
        return False

    try:
        # Retry loop: if PostgreSQL kills this transaction due to a deadlock (rare but
        # possible with external writers), wait briefly and retry up to 2 times before
        # giving up. A small random jitter avoids retry storms when two sessions race.
        _MAX_DEADLOCK_RETRIES = 2
        for _attempt in range(_MAX_DEADLOCK_RETRIES + 1):
            with get_pooled_connection() as conn:
                if not conn:
                    return False
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        SELECT
                            COALESCE(last_risk_level, 'low'),
                            COALESCE(safety_action_taken, 'none'),
                            COALESCE(detected_tone, 'neutral'),
                            user_facts_json,
                            COALESCE(reply_agent_source, 'coach')
                        FROM chat_analysis
                        WHERE user_id = %s AND session_id = %s
                        ORDER BY COALESCE(last_updated, created_at) DESC
                        LIMIT 1
                        """,
                        (user_id, session_id_norm),
                    )
                    row = cur.fetchone()
                    if row:
                        risk, safety, tone, facts_raw, reply_source = row
                        facts = _coerce_facts_payload(facts_raw) if facts_raw else {}
                    else:
                        risk, safety, tone, reply_source = "low", "none", "neutral", "coach"
                        facts = {}

                    cur.execute(
                        """
                        SELECT
                            user_message,
                            assistant_response
                        FROM chat_messages
                        WHERE user_id = %s AND session_id = %s
                        ORDER BY user_msg_timestamp ASC
                        """,
                        (user_id, session_id_norm),
                    )
                    session_rows = cur.fetchall()
                    if not session_rows:
                        return False

                    derived = _derive_session_analysis_from_rows(session_rows)
                    latest_user_input = derived.get("latest_user_input") or ""

                    tone_norm = str(tone or "").strip().lower()
                    derived_tone = str(derived.get("tone") or "").strip().lower()
                    if (tone_norm in {"", "neutral", "none", "null", "n/a"} and
                            derived_tone and derived_tone not in {"neutral", "none", "null", "n/a"}):
                        tone = derived_tone

                    derived_facts = derived.get("facts", {})
                    if isinstance(derived_facts, dict) and derived_facts:
                        _deep_merge_facts(facts, derived_facts)

                    risk = _normalize_risk(risk)
                    safety_norm = str(safety or "").strip().lower()
                    if safety_norm in {"", "none", "null", "n/a"}:
                        if risk == "high":
                            safety = "immediate"
                        elif risk == "medium":
                            safety = "supportive"
                        else:
                            safety = "normal"

                    tone = str(tone or "").strip().lower() or "neutral"
                    reply_source = str(reply_source or "").strip().lower() or "coach"
                    # Preload succeeded — break out of the retry loop.
                    break
                except errors.DeadlockDetected as e:
                    # PostgreSQL detected a deadlock and aborted this transaction.
                    # The threading lock above prevents this in normal cases; this
                    # retry handles the rare race with an external writer (e.g. a
                    # concurrent save_chat_message from another session thread).
                    if _attempt < _MAX_DEADLOCK_RETRIES:
                        wait = 0.1 * (2 ** _attempt)  # 100 ms, then 200 ms
                        logger.warning(
                            "finalize_session_analysis deadlock on attempt %d/%d for session %s — retrying in %.2fs",
                            _attempt + 1, _MAX_DEADLOCK_RETRIES, session_id_norm, wait,
                        )
                        time.sleep(wait)
                        continue
                    logger.error("finalize_session_analysis preload failed after %d retries: %s", _MAX_DEADLOCK_RETRIES, e)
                    return False
                except Exception as e:
                    logger.error("finalize_session_analysis preload failed: %s", e)
                    return False
                finally:
                    cur.close()
        else:
            # Exhausted all retry attempts without a successful break.
            return False

    finally:
        # Always release the per-session lock so future calls can proceed.
        session_lock.release()

    result = update_master_analysis(
        user_id=user_id,
        session_id=session_id_norm,
        risk=risk,
        safety=safety,
        tone=tone,
        facts=facts,
        summary="",
        user_input=latest_user_input,
        reply_source=reply_source,
        finalize_summary=True,
    )

    # Also persist facts into user_memory here, at session finalization — not just
    # relying on the per-turn LLM memory agent (pages.py's _save_bg), which only
    # writes a fact when its own "new_fact" JSON happens to be non-empty for that
    # exact turn. Observed directly: a real message clearly containing new facts
    # ("stressed because of work", "not sleeping properly") got a genuinely empty
    # new_fact:{} from the LLM, so nothing was ever stored. _extract_facts_from_messages
    # (the same deterministic extractor already powering chat_analysis reliably) is
    # not dependent on the LLM's per-turn judgment, so use it here as the dependable
    # path — the LLM per-turn path still runs too and can only add rows sooner.
    if result and facts:
        try:
            for key, value in facts.items():
                if key in {"topic_state", "key", "value"}:
                    continue
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key in {"topic_state", "key", "value"} or sub_key.startswith("_"):
                            continue
                        sub_value_text = str(sub_value).strip()
                        if sub_value_text and len(sub_value_text) > 1:
                            store_user_memory(
                                user_id=user_id,
                                memory_type="long_term_memory",
                                memory_key=sub_key,
                                memory_value=sub_value_text,
                                confidence=0.8,
                            )
                else:
                    value_text = str(value).strip()
                    if value_text and len(value_text) > 1:
                        store_user_memory(
                            user_id=user_id,
                            memory_type="long_term_memory",
                            memory_key=key,
                            memory_value=value_text,
                            confidence=0.8,
                        )
        except Exception as e:
            logger.warning("Session-finalize memory storage skipped: %s", e)

    # Auto-ingest session facts into RAG after successful finalization.
    # Runs in a daemon thread — never blocks the response path.
    # Facts are the richest long-term signal: occupation, stressors, sleep, etc.
    if result and facts:
        try:
            from rag import ingest_to_rag_async
            fact_lines = []
            for k, v in facts.items():
                if isinstance(v, dict):
                    for sk, sv in v.items():
                        if sk and sv:
                            fact_lines.append(f"{sk}: {sv}")
                elif k and v:
                    fact_lines.append(f"{k}: {v}")
            if fact_lines:
                fact_text = f"Session facts (tone={tone}, risk={risk}):\n" + "\n".join(fact_lines[:20])
                ingest_to_rag_async(user_id, fact_text, "session_facts", session_id_norm)
        except Exception as _ing_err:
            logger.warning("RAG ingest async failed: %s", _ing_err)

    return result


def rewrite_recent_session_summaries(user_id, count=2):
    """Force-regenerate summaries for the user's most recent sessions."""
    if not user_id:
        return 0

    try:
        limit = max(int(count), 1)
    except Exception:
        limit = 2

    with get_pooled_connection() as conn:
        if not conn:
            return 0
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT cm.session_id
                FROM chat_messages cm
                WHERE cm.user_id = %s
                GROUP BY cm.session_id
                ORDER BY MAX(COALESCE(cm.bot_msg_timestamp, cm.user_msg_timestamp)) DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()
        except Exception as e:
            logger.warning("rewrite_recent_session_summaries query failed: %s", e)
            return 0
        finally:
            cur.close()

    rewritten = 0
    for row in rows:
        sess_id = str(row[0]) if row and row[0] else ""
        if not sess_id:
            continue
        try:
            if finalize_session_analysis(user_id, sess_id):
                rewritten += 1
        except Exception as e:
            logger.warning("Failed to rewrite summary for session %s: %s", sess_id, e)
    return rewritten


# ===================== CONSOLIDATED FETCH =====================

def fetch_selective_context(user_id, session_id, memory_types, neg_words=None, query_text=None):
    """
    Fetch ONLY the specific memory types needed for this intent.

    Args:
        user_id: User ID
        session_id: Session ID
        memory_types: List of memory types to fetch
            - "current_session": Recent messages in this session
            - "long_term_memory": User's personal facts/history
            - "onboarding_profile": User's onboarding answers
            - "rag_documents": Knowledge base chunks
            - "previous_sessions": Facts from past sessions
        neg_words: Whether negative words detected (for mood patterns)
        query_text: Query for RAG retrieval

    Returns: memory_data dict with ONLY requested memory types
    """
    import time
    fetch_start = time.time()
    memory_data = {}

    with get_pooled_connection() as conn:
        if not conn:
            logger.warning("fetch_selective_context: No database connection available")
            return {}

        cur = conn.cursor()
        try:
            # Fetch only requested memory types

            if "current_session" in memory_types:
                """Fetch recent messages in this session"""
                session_id_norm = _coerce_session_id(session_id)
                if session_id_norm:
                    try:
                        cur.execute("""
                            SELECT user_message, assistant_response, user_msg_timestamp
                            FROM chat_messages
                            WHERE user_id = %s AND session_id = %s
                            ORDER BY message_id DESC
                            LIMIT 8
                        """, (user_id, session_id_norm))
                        recent = cur.fetchall()
                        if recent:
                            memory_data["recent_messages"] = [
                                {"user": r[0], "assistant": r[1], "timestamp": r[2]}
                                for r in recent
                            ]
                    except Exception as e:
                        logger.warning("current_session fetch failed: %s", e)

            if "long_term_memory" in memory_types:
                """Fetch user's personal facts/history"""
                try:
                    cur.execute("""
                        SELECT memory_key, memory_value
                        FROM user_memory
                        WHERE user_id = %s AND memory_type = 'long_term_memory'
                        ORDER BY last_updated DESC
                        LIMIT 20
                    """, (user_id,))
                    facts = cur.fetchall()
                    if facts:
                        memory_data["facts"] = {k: v for k, v in facts}
                except Exception as e:
                    logger.warning("long_term_memory fetch failed: %s", e)

            if "onboarding_profile" in memory_types:
                """Fetch user's onboarding answers"""
                try:
                    cur.execute("""
                        SELECT question, answer
                        FROM onboarding_que
                        WHERE user_id = %s
                        ORDER BY created_at ASC
                    """, (user_id,))
                    onboarding = cur.fetchall()
                    if onboarding:
                        memory_data["onboarding"] = [
                            {"question": q, "answer": a}
                            for q, a in onboarding
                        ]
                except Exception as e:
                    logger.warning("onboarding_profile fetch failed: %s", e)

            if "rag_documents" in memory_types and query_text:
                """Fetch knowledge base chunks relevant to query"""
                if query_text and _should_use_rag(query_text):
                    try:
                        from rag import (
                            retrieve_relevant_chunks_with_metadata,
                            filter_chunks_by_relevance,
                            reformulate_query,
                        )
                        search_query = reformulate_query(query_text)
                        logger.info("RAG search: %s", search_query)
                        # Use the metadata+threshold path, not the bare
                        # top-k nearest-neighbor one: this is the function
                        # that actually reaches the Coach's prompt (see
                        # engine.py::_call_agent's common_parts assembly),
                        # so it needs the same relevance bar as the
                        # analytics-tracking path in pages.py, not an
                        # unfiltered top-3 regardless of how weak the
                        # match is. Found missing by evaluations/rag_eval.py.
                        full_chunks, rag_metadata = retrieve_relevant_chunks_with_metadata(
                            user_id, search_query, top_k=10
                        )
                        # metadata's chunk_text is truncated to 500 chars for
                        # DB-storage display - use the untruncated full_chunks
                        # (same order) for what actually reaches the prompt.
                        by_doc_id = {c["doc_id"]: full_chunks[i] for i, c in enumerate(rag_metadata)}
                        relevant = filter_chunks_by_relevance(rag_metadata)
                        rag_chunks = [by_doc_id[c["doc_id"]] for c in relevant[:3]]
                        if rag_chunks:
                            memory_data["rag_context"] = rag_chunks
                    except Exception as e:
                        logger.warning("rag_documents fetch failed: %s", e)

            if "previous_sessions" in memory_types:
                """Fetch actual session summaries from previous sessions with tone, facts, and date"""
                try:
                    # Use fetch_all_session_summaries to get proper session history with summaries
                    # CRITICAL: Pass session_id to exclude current session from "previous" classification
                    session_history = fetch_all_session_summaries(user_id, limit=10, exclude_session_id=session_id, _cur=cur)
                    if session_history:
                        memory_data["session_history"] = session_history
                        # Also add merged facts from all previous sessions
                        merged_facts = {}
                        for session in session_history:
                            if session.get("facts"):
                                _deep_merge_facts(merged_facts, session["facts"])
                        if merged_facts:
                            # Merge with any existing facts dict
                            if "facts" not in memory_data:
                                memory_data["facts"] = {}
                            _deep_merge_facts(memory_data["facts"], merged_facts)
                        logger.info(f"✅ Fetched {len(session_history)} previous sessions for continuity")
                        for idx, sess in enumerate(session_history[:3]):
                            logger.info(f"   Session {idx+1}: {sess.get('date')} - {sess.get('summary', '')[:80]}")
                    else:
                        logger.warning("⚠️  No previous sessions found in chat_analysis table")
                except Exception as e:
                    logger.warning("❌ previous_sessions fetch failed: %s", e)

            # Mood patterns only if negative signals present
            if neg_words and ("long_term_memory" in memory_types or "emotional_support" in memory_types):
                try:
                    mood_patterns = analyze_mood_patterns(user_id, days=7, _cur=cur)
                    if mood_patterns:
                        memory_data["mood_patterns"] = mood_patterns
                except Exception as e:
                    logger.warning("mood_patterns fetch failed: %s", e)

            fetch_elapsed = time.time() - fetch_start
            logger.info(
                "Selective memory fetch (%.2fs): types=[%s] | got_keys=%s",
                fetch_elapsed, ", ".join(memory_types), list(memory_data.keys())
            )
            return memory_data

        finally:
            cur.close()


def fetch_all_user_context(user_id, session_id, neg_words=None, query_text=None):
    """Single-connection fetch of ALL user context needed before LLM call.

    Consolidates fetch_master_memory + fetch_recent_messages + analyze_mood_patterns
    into ONE database connection (#1, #2, #3).

    Returns a ready-to-use memory_data dict.
    """
    import time
    fetch_start = time.time()
    with get_pooled_connection() as conn:
        if not conn:
            logger.warning("fetch_all_user_context: No database connection available")
            return {
                "summary": "First conversation.",
                "facts": {},
                "last_tone": "neutral",
                "last_risk": "low",
                "mood_history": [],
                "session_history": [],
                "recent_messages": [],
            }
        cur = conn.cursor()
        try:
            memory_data = fetch_master_memory(user_id, search_text=query_text, _cur=cur)
            memory_data["user_memory"] = fetch_user_memory(user_id)
            memory_data["recent_messages"] = fetch_recent_messages(user_id, session_id, limit=16, _cur=cur)

            # Mood patterns only when negative signals present — uncommented to feed
            # mood_patterns into memory_data so _format_long_term_memory can inject it.
            if neg_words:
                mood_patterns = analyze_mood_patterns(user_id, days=7, _cur=cur)
                if mood_patterns:
                    memory_data["mood_patterns"] = mood_patterns

            # RAG retrieval — find the top 3 most semantically relevant chunks.
            # Two improvements applied before retrieval:
            #   1. query_text already contains last 2 turns (enriched in pages.py)
            #      so RAG understands context like "what should I do about it?"
            #   2. reformulate_query rewrites the conversational query into
            #      search-optimized keywords before embedding — improves vector match.
            if query_text and _should_use_rag(query_text):
                try:
                    from rag import retrieve_relevant_chunks, reformulate_query
                    search_query = reformulate_query(query_text)
                    # custom changes start
                    # custom changes end
                    rag_chunks = retrieve_relevant_chunks(user_id, search_query, top_k=3)
                    if rag_chunks:
                        memory_data["rag_context"] = rag_chunks
                except Exception as _rag_err:
                    logger.warning("RAG retrieval skipped: %s", _rag_err)
                    # custom changes start
                    # custom changes end
            elif query_text:
                # custom changes start
                pass
                # custom changes end

            # Onboarding data for personalization (#28)
            try:
                cur.execute("SELECT question, answer FROM onboarding_que WHERE user_id = %s ORDER BY created_at ASC", (user_id,))
                onboarding = cur.fetchall()
                if onboarding:
                    memory_data["onboarding"] = [{"question": q, "answer": a} for q, a in onboarding]
            except Exception as e:
                logger.warning(f"Onboarding fetch failed (table may not exist): {e}")

            fetch_elapsed = time.time() - fetch_start
            facts_count = len(memory_data.get("facts", {})) if isinstance(memory_data.get("facts"), dict) else 0
            logger.info(
                "Memory fetch complete in %.2fs: facts=%d | recent_msgs=%d | has_mood_patterns=%s | has_onboarding=%s | summary_len=%d",
                fetch_elapsed, facts_count, len(memory_data.get("recent_messages", [])),
                "yes" if memory_data.get("mood_patterns") else "no",
                "yes" if memory_data.get("onboarding") else "no",
                len(memory_data.get("summary", ""))
            )
            return memory_data
        finally:
            cur.close()

############################### Added by SB ###############################
# New table: user_memory
def create_memory_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            memory_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
            memory_type TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            memory_value TEXT,
            confidence FLOAT DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, memory_type, memory_key)
        );
    """)

def create_rag_documents_table(cur):
    """
    Creates the rag_documents table used for RAG retrieval.
    Stores embeddings for pgvector semantic search (<=>).
    UNIQUE(user_id, content) prevents duplicate ingestion of the same chunk.
    """
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception:
        pass  # pgvector not available — json fallback will be used automatically

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            doc_id         SERIAL PRIMARY KEY,
            user_id        INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
            content        TEXT NOT NULL,
            content_hash   VARCHAR(32),
            embedding      vector(768),
            source         VARCHAR(200),
            session_id     UUID,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # content_hash column migration — adds it if table already exists without it
    try:
        cur.execute("ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32);")
    except Exception:
        pass
    # Unique index on hash — always 32 chars, never hits btree size limit
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS rag_documents_hash_idx
            ON rag_documents(content_hash)
            WHERE content_hash IS NOT NULL;
        """)
    except Exception:
        pass
    # Allow NULL user_id for global knowledge documents (PDFs, ebooks).
    # A NULL user_id means the chunk belongs to everyone — retrieved for all users.
    try:
        cur.execute("ALTER TABLE rag_documents ALTER COLUMN user_id DROP NOT NULL;")
    except Exception:
        pass  # already nullable
    # Unique index handles (NULL, content) correctly in PostgreSQL
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS rag_documents_unique_idx
            ON rag_documents(COALESCE(user_id::TEXT, 'global'), content);
        """)
    except Exception:
        pass
    cur.execute("""
        CREATE INDEX IF NOT EXISTS rag_documents_user_idx
        ON rag_documents(user_id);
    """)

# memory insertion function with confidence score and timestamp update
def store_user_memory(user_id, memory_type, memory_key, memory_value, confidence=1.0):
    """
    Insert or update user memory.

    If the same (user_id, memory_type, memory_key) already exists,
    it updates the value instead of creating duplicates.
    """
    with get_pooled_connection() as conn:
        if not conn:
            return False

        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO user_memory
                (user_id, memory_type, memory_key, memory_value, confidence, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW())

                ON CONFLICT (user_id, memory_type, memory_key)
                DO UPDATE SET
                    memory_value = EXCLUDED.memory_value,
                    confidence = EXCLUDED.confidence,
                    last_updated = NOW();
            """, (user_id, memory_type, memory_key, memory_value, confidence))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"store_user_memory error: {e}")
            return False

        finally:
            cur.close()           

# memory retrieval function to fetch all memories for a user
def fetch_user_memory(user_id):
    with get_pooled_connection() as conn:
        if not conn:
            return {}
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT memory_type, memory_key, memory_value
                FROM user_memory
                WHERE user_id = %s
                ORDER BY last_updated DESC
            """, (user_id,))
            rows = cur.fetchall()

            memory = {
                "profile": {},
                "emotion_history": {},
            }

            for mtype, key, value in rows:
                if mtype not in memory:
                    memory[mtype] = {}
                memory[mtype][key] = value

            return memory

        except Exception as e:
            logger.error(f"fetch_user_memory error: {e}")
            return {}
        finally:
            cur.close()  

def create_users_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        serial_no SERIAL,
        user_id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE,
        full_name VARCHAR(100),
        dob DATE,
        gender VARCHAR(20),
        role VARCHAR(20),
        country VARCHAR(50),
        state VARCHAR(50),
        city VARCHAR(50),
        pincode VARCHAR(10),
        mobile_number VARCHAR(15) UNIQUE,
        is_verified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

def add_email_password_columns(cur):
    """Add email and password_hash columns to users table if they don't exist."""
    try:
        # Add email column (NOT NULL with default for existing rows)
        cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS email VARCHAR(255) NOT NULL DEFAULT '';
        """)
        logger.info("Added email column to users table")
    except Exception as e:
        logger.debug(f"Email column migration: {_compact_error(e)}")
    
    try:
        # Add password_hash column (NOT NULL with default for existing rows)
        cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NOT NULL DEFAULT '';
        """)
        logger.info("Added password_hash column to users table")
    except Exception as e:
        logger.debug(f"Password_hash column migration: {_compact_error(e)}")

def add_trusted_adult_columns(cur):
    """Add trusted_adult_name and trusted_adult_phone columns to users table if they don't exist."""
    try:
        cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS trusted_adult_name VARCHAR(100) DEFAULT '';
        """)
        logger.info("Added trusted_adult_name column to users table")
    except Exception as e:
        logger.debug(f"Trusted adult name column migration: {_compact_error(e)}")

    try:
        cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS trusted_adult_phone VARCHAR(15) DEFAULT '';
        """)
        logger.info("Added trusted_adult_phone column to users table")
    except Exception as e:
        logger.debug(f"Trusted adult phone column migration: {_compact_error(e)}")

def create_chat_messages_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        serial_no SERIAL,
        message_id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        session_id UUID NOT NULL,
        user_message TEXT,
        assistant_response TEXT,
        user_msg_timestamp TIMESTAMP,
        bot_msg_timestamp TIMESTAMP,
        latency_seconds DOUBLE PRECISION,
        CONSTRAINT chat_messages_user_id_fkey
            FOREIGN KEY (user_id)
            REFERENCES users(user_id)
            ON DELETE CASCADE
    );
    """)                          

def add_chat_messages_architecture_columns(cur):
    """Add locked-architecture columns to chat_messages without removing legacy columns."""
    statements = [
        # "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP;",
        # "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_msg TEXT;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'low';",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS safety_action VARCHAR(30) DEFAULT 'normal';",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS intent_label VARCHAR(100);",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS response_mode VARCHAR(100);",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS memory_used BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS memory_type TEXT;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS escalation_flag BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS final_reply_agent VARCHAR(50) DEFAULT 'coach';",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS fallback_triggered BOOLEAN DEFAULT FALSE;",
        # "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS rag_context JSONB;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS rag_used BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS doc_id INTEGER[];",
        # Convert existing doc_id column from INTEGER to INTEGER[] if it exists as INTEGER
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chat_messages' AND column_name = 'doc_id'
                AND data_type = 'integer'
            ) THEN
                ALTER TABLE chat_messages ALTER COLUMN doc_id TYPE integer[] USING ARRAY[doc_id];
            END IF;
        END $$;
        """,
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            logger.warning(f"chat_messages migration warning: {e}")

def rename_chat_analysis_visible_serial_no(cur):
    """Rename visible_serial_no column to serial_no in chat_analysis table."""
    try:
        cur.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'chat_analysis' AND column_name = 'visible_serial_no'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'chat_analysis' AND column_name = 'serial_no'
                ) THEN
                    ALTER TABLE chat_analysis RENAME COLUMN visible_serial_no TO serial_no;
                END IF;
            END $$;
        """)
        logger.info("Renamed visible_serial_no to serial_no in chat_analysis table")
    except Exception as e:
        logger.warning(f"Rename visible_serial_no failed: {e}")


def renumber_chat_messages_serial_no(cur):
    """Renumber all serial_no values sequentially to remove gaps.

    This fixes existing gaps by renumbering rows based on message_id order.
    Run this once after switching to manual serial_no calculation.
    """
    try:
        cur.execute("""
            WITH renumbered AS (
                SELECT message_id, ROW_NUMBER() OVER (ORDER BY message_id) AS new_serial
                FROM chat_messages
            )
            UPDATE chat_messages cm
            SET serial_no = r.new_serial
            FROM renumbered r
            WHERE cm.message_id = r.message_id
        """)
        logger.info("Renumbered chat_messages.serial_no sequentially (gaps removed)")
    except Exception as e:
        logger.warning(f"Renumber serial_no failed: {e}")


def fix_chat_messages_serial_sequence(cur):
    """Comprehensively fix SERIAL sequence corruption in chat_messages table.

    Uses PostgreSQL's setval() which is more reliable than ALTER SEQUENCE.
    Handles cases where sequences are corrupted or misaligned with table data.
    """
    try:
        # Clean up any corrupted backup tables from failed migration attempts
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'chat_messages_old' LIMIT 1
        """)
        if cur.fetchone():
            logger.warning("Found corrupted chat_messages_old - cleaning up...")
            cur.execute("DROP TABLE IF EXISTS chat_messages_old CASCADE")
            logger.info("✓ Cleaned up corrupted backup table")

        # Get the max IDs currently in the table
        cur.execute("SELECT MAX(message_id), MAX(serial_no) FROM chat_messages")
        result = cur.fetchone()
        max_message_id = result[0] if result[0] else 0
        max_serial_no = result[1] if result[1] else 0

        logger.info(f"Database state: max_message_id={max_message_id}, max_serial_no={max_serial_no}")

        # Find sequences for this table (they may have different names than expected)
        cur.execute("""
            SELECT sequence_name
            FROM information_schema.sequences
            WHERE sequence_schema = 'public'
            AND sequence_name LIKE 'chat_messages%'
            ORDER BY sequence_name
        """)

        sequences = [row[0] for row in cur.fetchall()]
        logger.info(f"Found sequences: {sequences}")

        # If no sequences found at all, we have a critical problem
        if not sequences:
            logger.error("❌ CRITICAL: No sequences found for chat_messages table!")
            logger.error("The table may be in an inconsistent state. Attempting recovery...")

            # Try to find the actual sequence name by querying the column definition
            cur.execute("""
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'chat_messages' AND column_name = 'message_id'
            """)
            col_default = cur.fetchone()
            if col_default:
                logger.info(f"Current message_id DEFAULT: {col_default[0]}")

        # Reset all found sequences using setval() which is more reliable
        for seq_name in sequences:
            try:
                # Use setval to set the sequence to max_id + 1
                # setval(regclass, bigint, is_called=true) where is_called=true means
                # the next nextval() call will return bigint + 1
                new_value = max_message_id + 1 if 'message_id' in seq_name else max_serial_no + 1
                cur.execute(f"SELECT setval('{seq_name}'::regclass, %s, true)", (new_value,))
                logger.info(f"✓ Reset {seq_name} to {new_value}")
            except Exception as e:
                logger.warning(f"Could not reset sequence {seq_name}: {e}")

        logger.info("✓ Database sequence repair completed")

    except Exception as e:
        logger.error(f"Critical error in serial sequence fix: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

def create_chat_analysis_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_analysis (
        serial_no INTEGER UNIQUE,
        analysis_id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        session_id UUID NOT NULL,
        last_risk_level VARCHAR(20) DEFAULT 'low',
        safety_action_taken TEXT DEFAULT 'none',
        detected_tone VARCHAR(100) DEFAULT 'neutral',
        user_facts_json JSONB DEFAULT '{}',
        summary_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reply_agent_source VARCHAR(50) DEFAULT 'coach',
        CONSTRAINT chat_analysis_user_id_fkey
            FOREIGN KEY (user_id)
            REFERENCES users(user_id)
    );
    """)    

def add_chat_analysis_architecture_columns(cur):
    """Add locked-architecture columns to chat_analysis without removing legacy columns."""
    statements = [
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS session_summary TEXT;",
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS dominant_emotion VARCHAR(100);",
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS repeated_stressors TEXT;",
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS risk_trend VARCHAR(50);",
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS escalation_flag BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE chat_analysis ADD COLUMN IF NOT EXISTS recommended_followup TEXT;",
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            logger.warning(f"chat_analysis migration warning: {e}")

def add_chat_analysis_unique_constraint(cur):
    """
    chat_analysis was created without a uniqueness guarantee on (user_id, session_id),
    but update_master_analysis() upserts with `ON CONFLICT (user_id, session_id)`.
    Without a matching unique index, Postgres rejects every upsert with
    InvalidColumnReference, which silently breaks all writes to this table.
    A unique index satisfies ON CONFLICT just as well as a named constraint.
    """
    try:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS chat_analysis_user_session_idx
            ON chat_analysis(user_id, session_id);
            """
        )
    except Exception as e:
        logger.warning(f"chat_analysis unique index migration warning: {e}")


def drop_legacy_agent_columns(cur):
    """Remove legacy agent columns (safety_agent, memory_agent, orchestrator_agent, coach_agent)."""
    statements = [
        "ALTER TABLE chat_messages DROP COLUMN IF EXISTS agent_safety;",
        "ALTER TABLE chat_messages DROP COLUMN IF EXISTS agent_memory;",
        "ALTER TABLE chat_messages DROP COLUMN IF EXISTS agent_orchestrator;",
        "ALTER TABLE chat_messages DROP COLUMN IF EXISTS agent_coach;",
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
            logger.info(f"Migration executed: {stmt}")
        except Exception as e:
            logger.warning(f"Drop legacy agent columns migration warning: {e}")

def add_rag_tracking_columns(cur):
    """Add RAG tracking columns for minimal RAG proof setup (rag_used already exists)."""
    statements = [
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS rag_source TEXT;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS retrieved_count INTEGER;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS retrieval_score FLOAT;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS grounded_flag BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS rag_benefit_flag BOOLEAN DEFAULT FALSE;",
    ]
    for stmt in statements:
        try:
            cur.execute(stmt)
            logger.info(f"RAG tracking migration: {stmt[:60]}...")
        except Exception as e:
            logger.debug(f"RAG tracking column migration: {_compact_error(e)}")

def create_onboarding_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_que (
        serial_no SERIAL,
        onboard_id SERIAL PRIMARY KEY,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT onboarding_que_user_id_fkey
            FOREIGN KEY (user_id)
            REFERENCES users(user_id)
            ON DELETE CASCADE
    );
    """)    


def _diagnose_database_health(cur):
    """Quick diagnostic of database health - logs status for debugging."""
    try:
        # Check table existence
        cur.execute("""
            SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_messages')
        """)
        result = cur.fetchone()
        table_exists = result[0] if result else False

        # Check data in table
        cur.execute("SELECT COUNT(*) FROM chat_messages")
        result = cur.fetchone()
        row_count = result[0] if result else 0

        # Check sequences
        cur.execute("""
            SELECT sequence_name FROM information_schema.sequences
            WHERE sequence_schema = 'public' AND sequence_name LIKE 'chat_messages%'
            ORDER BY sequence_name
        """)
        sequences = [row[0] for row in cur.fetchall()]

        logger.info(f"📊 Database Diagnostics:")
        logger.info(f"   ✓ chat_messages table exists: {table_exists}")
        logger.info(f"   ✓ Rows in chat_messages: {row_count}")
        logger.info(f"   ✓ Sequences found: {sequences}")

        return table_exists

    except Exception as e:
        logger.warning(f"Diagnostic check warning: {e}")
        return False


def save_trusted_adult_info(user_id, trusted_adult_name, trusted_adult_phone):
    """Save or update trusted adult information for a user."""
    try:
        with get_pooled_connection() as conn:
            if not conn:
                logger.error("Failed to get database connection for saving trusted adult info")
                return False

            cur = conn.cursor()
            cur.execute("""
                UPDATE users
                SET trusted_adult_name = %s, trusted_adult_phone = %s
                WHERE user_id = %s
            """, (trusted_adult_name, trusted_adult_phone, user_id))

            conn.commit()
            logger.info(f"Saved trusted adult info for user {user_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to save trusted adult info: {e}")
        return False


def fetch_trusted_adult_info(user_id):
    """Fetch trusted adult information for a user."""
    try:
        with get_pooled_connection() as conn:
            if not conn:
                logger.error("Failed to get database connection for fetching trusted adult info")
                return None

            cur = conn.cursor()
            cur.execute("""
                SELECT trusted_adult_name, trusted_adult_phone
                FROM users
                WHERE user_id = %s
            """, (user_id,))

            result = cur.fetchone()
            if result:
                return {
                    "trusted_adult_name": result[0] or "",
                    "trusted_adult_phone": result[1] or ""
                }
            return {"trusted_adult_name": "", "trusted_adult_phone": ""}
    except Exception as e:
        logger.error(f"Failed to fetch trusted adult info: {e}")
        return {"trusted_adult_name": "", "trusted_adult_phone": ""}


_db_initialized = False


def initialize_database():
    # Streamlit reruns the entire app.py script on every user interaction
    # (every click, every chat message), and app.py calls this unconditionally
    # at module level. Without this guard, the full schema/migration sequence
    # below — measured at 10-13 seconds of real Neon round-trips — was
    # re-running on every single interaction, not once at process startup.
    # Schema state doesn't change per interaction, so do the real work once
    # per process and let every later call return immediately.
    global _db_initialized
    if _db_initialized:
        return True

    with get_pooled_connection() as conn:
        if not conn:
            return False

        cur = conn.cursor()

        # All of the steps below share one uncommitted transaction. If any single
        # step fails (e.g. a transient Neon hiccup, or two overlapping app reruns
        # racing on the same DDL), Postgres aborts the whole transaction and every
        # later statement raises InFailedSqlTransaction — which, uncaught, used to
        # propagate out of this function, out of app.py's module-level call, and
        # crash the entire page with a raw traceback instead of the app. This is
        # observed and reproducible, not hypothetical: it happened during testing.
        # Catch it here so a transient failure degrades to "try again next rerun"
        # instead of showing every user a broken page.
        try:
            create_users_table(cur)
            add_email_password_columns(cur)
            add_trusted_adult_columns(cur)
            create_chat_messages_table(cur)
            create_chat_analysis_table(cur)
            create_onboarding_table(cur)
            create_memory_table(cur)
            create_rag_documents_table(cur)

            # Apply the additive schema migrations required by the current save paths.
            # Every statement uses `ADD COLUMN IF NOT EXISTS`, so this is safe on both
            # a new database and an existing database.  These are not optional:
            # `save_chat_message` writes the chat metadata columns and
            # `update_master_analysis` writes the analysis columns.
            add_chat_messages_architecture_columns(cur)
            add_rag_tracking_columns(cur)
            add_chat_analysis_architecture_columns(cur)
            add_chat_analysis_unique_constraint(cur)

            conn.commit()

            # Log diagnostics before closing
            _diagnose_database_health(cur)
        except Exception as e:
            conn.rollback()
            logger.error(f"Database initialization failed, will retry on next run: {e}")
            return False
        finally:
            cur.close()

        logger.info("✅ Database initialization completed successfully")
        _db_initialized = True
        return True


def fetch_user_profile(user_id):
    """Fetch user profile data from database."""
    if not user_id:
        return None
    with get_pooled_connection() as conn:
        if not conn:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT user_id, username, full_name, dob, mobile_number, email, gender, role, country, state, city, pincode
                FROM users
                WHERE user_id = %s
                """,
                (user_id,)
            )
            row = cur.fetchone()
            if row:
                profile_data = {
                    "user_id": row[0],
                    "username": row[1],
                    "full_name": row[2],
                    "dob": row[3],
                    "mobile_number": row[4],
                    "email": row[5],
                    "gender": row[6],
                    "role": row[7],
                    "country": row[8],
                    "state": row[9],
                    "city": row[10],
                    "pincode": row[11],
                }
                return profile_data
            return None
        except Exception as e:
            logger.debug(f"Failed to fetch user profile: {e}")
            return None
        finally:
            cur.close()


def update_user_profile(user_id, **fields):
    """Update user profile fields in database."""
    allowed_fields = {"full_name", "dob", "mobile_number", "email", "gender", "role", "country", "state", "city", "pincode"}
    fields = {k: v for k, v in fields.items() if k in allowed_fields}

    if not fields:
        return False

    with get_pooled_connection() as conn:
        if not conn:
            return False
        cur = conn.cursor()
        try:
            set_clause = ", ".join([f"{k} = %s" for k in fields.keys()])
            values = list(fields.values()) + [user_id]

            cur.execute(
                f"UPDATE users SET {set_clause} WHERE user_id = %s",
                values
            )
            conn.commit()
            logger.info(f"Updated user {user_id} profile: {list(fields.keys())}")
            return True
        except Exception as e:
            logger.warning(f"Failed to update user profile: {e}")
            try:
                conn.rollback()
            except:
                pass
            return False
        finally:
            cur.close()
