"""
RAG (Retrieval-Augmented Generation) module for MindWell.

Handles:
  - Embedding text via Ollama's nomic-embed-text model
  - Storing user-specific knowledge chunks in rag_documents table (pgvector)
  - Retrieving the most semantically relevant chunks for a given query
  - Fallback: Python cosine similarity when pgvector is unavailable on Neon

Auto-ingestion sources:
  - Session summaries (after finalize_session_analysis)
  - Extracted facts (after update_master_analysis)
  - Onboarding answers (after save_onboarding)
"""

import hashlib
import json
import logging
import math
import os
import threading
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBED_MODEL     = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM       = 768   # nomic-embed-text output dimension
EMBED_TIMEOUT   = 15    # seconds — embedding is fast, 15s is generous

# Minimum cosine similarity for a retrieved chunk to be considered relevant
# enough to use. Single source of truth: this used to be a second copy
# hardcoded in pages.py (_filter_chunks_by_relevance), used only for
# analytics tracking - never the same value on purpose, just drift waiting
# to happen the same way COPING_KEYWORDS/CONTINUITY_MARKERS/_should_use_rag
# drifted apart elsewhere in this codebase. Now the one place that decides
# what counts as relevant, for both the analytics path and the actual
# prompt-injection path (database.py::fetch_selective_context).
RELEVANCE_THRESHOLD = 0.65

# Dedup cache: avoids re-embedding identical content within a process lifetime
_ingest_seen: set = set()
_ingest_seen_lock = threading.Lock()


# ===================== EMBEDDING =====================

def get_embedding(text: str) -> Optional[List[float]]:
    """
    Embed text using Ollama's nomic-embed-text model.
    Returns a list of floats (length 768) or None on failure.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/embeddings"
        resp = requests.post(
            url,
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=EMBED_TIMEOUT,
        )
        resp.raise_for_status()
        embedding = resp.json().get("embedding")
        if embedding and isinstance(embedding, list) and len(embedding) > 0:
            return [float(x) for x in embedding]
        logger.warning("RAG: Ollama returned empty embedding for model=%s", EMBED_MODEL)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("RAG: Ollama not reachable at %s — embedding skipped.", OLLAMA_BASE_URL)
        return None
    except Exception as e:
        logger.warning("RAG embedding failed: %s", e)
        return None


# ===================== QUERY REFORMULATION =====================

def reformulate_query(raw_query: str) -> str:
    """
    Rewrites a raw conversational query into a clean, search-optimized string
    using a fast Ollama call. This bridges the gap between how users talk and
    how knowledge is indexed.

    Example:
        raw:       "ugh i just cant sleep and my brain wont stop going"
        rewritten: "insomnia racing thoughts anxiety sleep techniques"

    Falls back to the raw query silently if Ollama is unavailable or slow.
    Uses a very tight token budget (40 tokens) so it adds minimal latency.
    """
    raw_query = (raw_query or "").strip()
    if not raw_query or len(raw_query) < 15:
        return raw_query

    system_prompt = (
        "You are a search query optimizer for a mental health knowledge base. "
        "Given a user's conversational message (which may include chat history), "
        "rewrite it as a concise search query of 5-10 keywords that will best "
        "retrieve relevant mental health information. "
        "Output ONLY the rewritten query — no explanation, no punctuation, no quotes."
    )
    user_input = f"Rewrite this as a search query:\n{raw_query[:600]}"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={
                "model": os.getenv("OLLAMA_FAST_MODEL", "llama3:latest"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_input},
                ],
                "stream": False,
                "keep_alive": "-1",
                "options": {"num_predict": 40, "temperature": 0.1, "num_ctx": 1024},
            },
            timeout=12,
        )
        resp.raise_for_status()
        rewritten = (resp.json().get("message", {}).get("content") or "").strip()
        if rewritten and len(rewritten) > 4:
            logger.info("RAG query reformulated: [%s] → [%s]", raw_query[:60], rewritten[:80])
            return rewritten
    except Exception as e:
        logger.debug("Query reformulation skipped (non-critical): %s", e)

    return raw_query  # fallback — original query is still valid


# ===================== COSINE FALLBACK =====================

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Python cosine similarity — used when pgvector is unavailable."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ===================== INGESTION =====================

def _content_hash(user_id, content: str) -> str:
    """
    MD5 hash of (user_id + content).
    Always 32 chars — safe for DB unique index (no btree size limit issues).
    Works across process restarts unlike the in-memory _ingest_seen cache.
    """
    key = f"{user_id}:{content}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def ingest_to_rag(user_id: int, content: str, source: str,
                  session_id: str = None) -> bool:
    """
    Embed content and store it in rag_documents.
    Duplicate detection uses MD5 hash checked against the DB — works across
    process restarts. In-memory cache is a fast-path for within-run dedup.

    Returns True on success, False on skip/failure.
    """
    from database import get_pooled_connection

    content = (content or "").strip()
    if not content or len(content) < 20:
        return False

    chash = _content_hash(user_id, content)

    # Fast path: in-memory dedup within the same process run
    with _ingest_seen_lock:
        if chash in _ingest_seen:
            return False
        _ingest_seen.add(chash)

    with get_pooled_connection() as conn:
        if not conn:
            return False
        cur = conn.cursor()
        try:
            # DB-level dedup: check hash before embedding (avoids Ollama call on dupes)
            cur.execute(
                "SELECT 1 FROM rag_documents WHERE content_hash = %s LIMIT 1",
                (chash,)
            )
            if cur.fetchone():
                return False  # already exists — skip silently

            # Embed only after confirming it's new
            embedding = get_embedding(content)
            if not embedding:
                logger.warning("RAG ingest skipped — embedding unavailable: user=%s source=%s", user_id, source)
                return False

            # Insert into rag_documents with pgvector embedding
            cur.execute(
                """
                INSERT INTO rag_documents
                    (user_id, content, content_hash, embedding, source, session_id)
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                """,
                (user_id, content, chash, str(embedding), source,
                 str(session_id) if session_id else None),
            )
            conn.commit()
            logger.info("RAG ingested: user=%s source=%s chars=%d", user_id, source, len(content))
            return True

        except Exception as e:
            err_str = str(e).lower()
            if "unique" in err_str or "duplicate" in err_str:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return False
            logger.warning("RAG ingest DB error: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            cur.close()


def ingest_to_rag_async(user_id: int, content: str, source: str,
                        session_id: str = None):
    """
    Fire-and-forget wrapper — runs ingest_to_rag in a daemon thread
    so it never blocks the main response path.
    """
    t = threading.Thread(
        target=ingest_to_rag,
        args=(user_id, content, source, session_id),
        daemon=True,
    )
    t.start()


# ===================== RETRIEVAL =====================

def get_crisis_resources(limit: int = 2) -> List[str]:
    """
    Deterministically fetch curated Crisis Resources content by category
    label - no embedding, no similarity threshold, can never silently
    return nothing just because a message didn't phrase itself close enough
    to how the chunk was worded.

    Added because evaluations/rag_eval.py found that embedding-similarity
    retrieval alone put genuine crisis messages (e.g. "I am thinking about
    ending my life") right at 0.646, just under the 0.65 relevance bar -
    meaning this exact content could be silently dropped for the messages
    that need it most. Crisis content is safety-critical and small in
    volume (3 curated chunks); it doesn't need semantic search to find it,
    it needs to always be there. This is called directly from the crisis
    path (pages.py), not as part of the normal similarity-based retrieval.
    """
    from database import get_pooled_connection

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT content
                FROM   rag_documents
                WHERE  source = 'Crisis Resources' AND user_id IS NULL
                ORDER  BY doc_id ASC
                LIMIT  %s
                """,
                (limit,),
            )
            return [r[0] for r in cur.fetchall() if r[0]]
        except Exception as e:
            logger.warning("get_crisis_resources error: %s", e)
            return []
        finally:
            cur.close()


def retrieve_relevant_chunks(user_id: int, query: str,
                             top_k: int = 3) -> List[str]:
    """
    Return the top_k most semantically relevant chunks for the query.
    Searches BOTH:
      - user-specific chunks  (user_id = this user)
      - global knowledge docs (user_id IS NULL — e.g. PDF knowledge base)

    Strategy:
      1. Embed the query via Ollama nomic-embed-text.
      2. Try pgvector cosine similarity ORDER BY <=> (fast, DB-side).
      3. If pgvector unavailable, fall back to Python cosine ranking.
    """
    from database import get_pooled_connection

    query = (query or "").strip()
    if not query:
        return []

    query_emb = get_embedding(query)
    if not query_emb:
        return []

    with get_pooled_connection() as conn:
        if not conn:
            return []
        cur = conn.cursor()
        try:
            # ── pgvector semantic search ──────────────────────────────────────
            cur.execute(
                """
                SELECT content
                FROM   rag_documents
                WHERE  (user_id = %s OR user_id IS NULL)
                  AND  embedding IS NOT NULL
                ORDER  BY embedding <=> %s::vector
                LIMIT  %s
                """,
                (user_id, str(query_emb), top_k),
            )
            rows = cur.fetchall()
            results = [r[0] for r in rows if r[0]]
            return results if results else []

        except Exception as e:
            logger.warning("RAG retrieval error: %s", e)
            return []
        finally:
            cur.close()


def retrieve_relevant_chunks_with_metadata(user_id: int, query: str,
                                           top_k: int = 3) -> tuple:
    """
    Return (chunks, metadata_list) for RAG tracking in chat_messages.

    Returns:
      (list[str], list[dict]) where each dict has:
        {doc_id, source, chunk_text, similarity_score}

    This allows storing exactly what chunk was used, from which source, and how relevant it was.
    similarity_score is cosine similarity (0-1 range, higher = more relevant).
    """
    from database import get_pooled_connection

    query = (query or "").strip()
    if not query:
        return [], []

    query_emb = get_embedding(query)
    if not query_emb:
        return [], []

    with get_pooled_connection() as conn:
        if not conn:
            return [], []
        cur = conn.cursor()
        try:
            # ── pgvector semantic search + get embeddings for scoring ──────────
            cur.execute(
                """
                SELECT doc_id, content, source, embedding
                FROM   rag_documents
                WHERE  (user_id = %s OR user_id IS NULL)
                  AND  embedding IS NOT NULL
                ORDER  BY embedding <=> %s::vector
                LIMIT  %s
                """,
                (user_id, str(query_emb), top_k),
            )
            rows = cur.fetchall()
            if rows:
                chunks = [r[1] for r in rows if r[1]]
                metadata = []
                for r in rows:
                    if r[1]:  # if content exists
                        doc_embedding = r[3]
                        similarity = 0.0
                        # Parse embedding string to list
                        if isinstance(doc_embedding, str):
                            try:
                                # Try direct JSON parse first
                                doc_emb_list = json.loads(doc_embedding)
                                if isinstance(doc_emb_list, list) and len(doc_emb_list) > 0:
                                    similarity = _cosine_similarity(query_emb, doc_emb_list)
                            except Exception as e:
                                logger.debug("Failed to parse embedding: %s", e)
                        elif isinstance(doc_embedding, (list, tuple)):
                            # If it's already a list/tuple, use it directly
                            try:
                                similarity = _cosine_similarity(query_emb, list(doc_embedding))
                            except Exception as e:
                                logger.debug("Cosine similarity calculation failed: %s", e)

                        metadata.append({
                            "doc_id": r[0],
                            "source": r[2] or "unknown",
                            "chunk_text": r[1][:500] if r[1] else "",
                            "similarity_score": round(max(0.0, min(1.0, similarity)), 3)
                        })
                return chunks, metadata
            return [], []

        except Exception as e:
            logger.warning("RAG retrieval error: %s", e)
            return [], []
        finally:
            cur.close()


def filter_chunks_by_relevance(rag_chunks, similarity_threshold: float = RELEVANCE_THRESHOLD):
    """
    Filter retrieved chunks (from retrieve_relevant_chunks_with_metadata) to
    keep only ones meeting the relevance bar. Moved here from
    pages.py::_filter_chunks_by_relevance so both the analytics-tracking
    path and the actual prompt-injection path (database.py) use the exact
    same function and threshold, not two independently-maintained copies.

    Returns chunks sorted by score (highest first).
    """
    if not rag_chunks:
        return []

    relevant = [
        chunk for chunk in rag_chunks
        if chunk.get("similarity_score", 0) >= similarity_threshold
    ]
    relevant.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

    logger.debug(
        "Chunk filtering: %d retrieved -> %d relevant (threshold >= %s)",
        len(rag_chunks), len(relevant), similarity_threshold,
    )
    return relevant
