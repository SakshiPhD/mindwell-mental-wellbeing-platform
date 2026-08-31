"""
Latency benchmark for the real chat pipeline - answers "where does the time
go," not just "how long does it take." Complements the real historical
P50/P95/P99 already sitting in chat_messages.latency_seconds (47 real
messages as of 2026-08-27: P50=9.47s, P95=33.67s, P99=41.05s) with a
per-component breakdown that isn't recorded anywhere today: routing,
memory fetch, RAG retrieval, and each agent call (safety/memory/coach).

Not a correctness eval like the other four - there's no pass/fail here,
just measurement. Runs the real pipeline functions (router_graph.route(),
database.py::fetch_selective_context, rag.py::get_crisis_resources,
engine.py::MultiAgentEngine.run_care_pipeline) the same way pages.py
actually calls them for 5 representative message types, using a
nonexistent user_id (999999) so this never touches real user data - same
privacy discipline as the RAG eval.

Requires live Ollama + a real DB per case, same as the RAG eval - this is
measuring real latency, so there's no meaningful offline version of it.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from database import fetch_selective_context  # noqa: E402
from engine import MultiAgentEngine  # noqa: E402
from pages import _detect_intent_from_prompt, _detect_extreme_crisis  # noqa: E402
from rag import get_crisis_resources  # noqa: E402

FAKE_USER_ID = 999999  # never a real account
COMPONENTS = ["routing_s", "memory_fetch_s", "rag_s", "crisis_resources_s",
              "agent_safety_s", "agent_memory_s", "agent_coach_s", "pipeline_total_s"]

# (label, message, has_session_context)
TEST_MESSAGES = [
    ("greeting", "hi", False),
    ("coping_request", "what are some healthy ways to cope with stress", False),
    ("emotional_support", "I've been really anxious about my exams and can't sleep well.", False),
    ("continuity_followup", "what did we talk about", True),
    ("crisis", "I dont want to live anymore", False),
]


def run_one(label: str, prompt: str, has_session_context: bool) -> dict:
    session_id = f"latency-benchmark-{label}"
    result = {"label": label, "prompt": prompt}

    t0 = time.time()
    detected_intent, required_memory = _detect_intent_from_prompt(prompt, has_session_context=has_session_context)

    is_extreme, crisis_risk, _ = _detect_extreme_crisis(prompt)
    risk_hint = "low"
    if crisis_risk in ("high", "medium"):
        detected_intent = "crisis" if crisis_risk == "high" else detected_intent
        risk_hint = "high" if crisis_risk == "high" else "medium"
        if detected_intent == "crisis":
            required_memory = ["current_session", "previous_sessions", "long_term_memory", "rag_documents"]
    result["routing_s"] = round(time.time() - t0, 3)
    result["detected_intent"] = detected_intent

    t0 = time.time()
    memory_data = fetch_selective_context(
        FAKE_USER_ID, session_id,
        memory_types=required_memory,
        neg_words=True,
        query_text=prompt,
    ) if required_memory else {}
    result["memory_fetch_s"] = round(time.time() - t0, 3)
    result["rag_s"] = memory_data.get("_fetch_timing", {}).get("rag_s", 0.0)

    t0 = time.time()
    if detected_intent == "crisis":
        crisis_chunks = get_crisis_resources()
        existing = memory_data.get("rag_context") or []
        memory_data["rag_context"] = crisis_chunks + [c for c in existing if c not in crisis_chunks]
    result["crisis_resources_s"] = round(time.time() - t0, 3)

    engine = MultiAgentEngine()
    response_text, _, analysis = engine.run_care_pipeline(prompt, memory_data, user_name="LatencyBenchmark")

    latency = analysis.get("latency", {})
    agent_s = latency.get("agent_s", {})
    result["pipeline_total_s"] = latency.get("pipeline_s", 0.0)
    result["agent_safety_s"] = agent_s.get("safety", 0.0)
    result["agent_memory_s"] = agent_s.get("memory", 0.0)
    result["agent_coach_s"] = agent_s.get("coach", 0.0)
    result["reply_len"] = len(response_text or "")
    result["total_wall_s"] = round(
        result["routing_s"] + result["memory_fetch_s"] + result["crisis_resources_s"] + result["pipeline_total_s"], 3
    )
    return result


def fetch_historical_percentiles():
    """Real P50/P95/P99 from actual conversations, not synthetic ones."""
    from database import get_pooled_connection
    try:
        with get_pooled_connection() as conn:
            if not conn:
                return None
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM chat_messages WHERE latency_seconds IS NOT NULL")
            n = cur.fetchone()[0]
            if not n:
                return None
            cur.execute("""
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_seconds),
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_seconds),
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_seconds)
                FROM chat_messages WHERE latency_seconds IS NOT NULL
            """)
            p50, p95, p99 = cur.fetchone()
            return {"n": n, "p50": p50, "p95": p95, "p99": p99}
    except Exception as e:
        print(f"Could not fetch historical percentiles: {e}")
        return None


def print_report(results: list):
    print("\n" + "=" * 100)
    print(f"{'message type':<22} | {'routing':>8} | {'mem_fetch':>9} | {'rag':>6} | "
          f"{'crisis_res':>10} | {'safety':>7} | {'memory':>7} | {'coach':>7} | {'total':>7}")
    print("-" * 100)
    for r in results:
        print(
            f"{r['label']:<22} | {r['routing_s']:>8.3f} | {r['memory_fetch_s']:>9.3f} | "
            f"{r['rag_s']:>6.3f} | {r['crisis_resources_s']:>10.3f} | {r['agent_safety_s']:>7.3f} | "
            f"{r['agent_memory_s']:>7.3f} | {r['agent_coach_s']:>7.3f} | {r['total_wall_s']:>7.3f}"
        )
    print("=" * 100)

    totals = {c: sum(r.get(c, 0.0) for r in results) for c in COMPONENTS if c != "pipeline_total_s"}
    grand_total = sum(totals.values())
    print("\nShare of total time across all test messages combined:")
    for name, val in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        pct = (val / grand_total * 100) if grand_total else 0
        print(f"  {name:<20} {val:>7.3f}s  ({pct:>5.1f}%)")

    biggest = max(totals, key=totals.get)
    print(f"\nBiggest contributor across these 5 messages: {biggest}")

    hist = fetch_historical_percentiles()
    if hist:
        print(f"\nReal historical baseline ({hist['n']} real messages, chat_messages.latency_seconds):")
        print(f"  P50={hist['p50']:.2f}s  P95={hist['p95']:.2f}s  P99={hist['p99']:.2f}s")
        bench_totals = [r["total_wall_s"] for r in results]
        print(f"This benchmark's range: {min(bench_totals):.2f}s - {max(bench_totals):.2f}s "
              f"(sanity check - should be in the same ballpark as the historical P50-P95 range, "
              f"not wildly faster/slower)")


def main():
    # Unlike the other evaluations/*.py scripts, this one still runs and
    # prints its console report even if LangSmith isn't configured (fail
    # open, matching tracing.py's own design) - there's no pass/fail here,
    # just measurement, so a missing LangSmith key shouldn't block it.
    # Found missing entirely until 2026-08-31: every prior benchmark run
    # (including both the Coach and Memory latency fixes) never called
    # this, so none of those runs ever showed up in LangSmith - the
    # per-agent breakdown this script prints to the console was real, but
    # invisible on the dashboard.
    from tracing import configure_tracing
    traced = configure_tracing(environment="development")
    if traced:
        print("LangSmith tracing: ON - this run's traces will appear in the LangSmith project.\n")
    else:
        print("LangSmith tracing: OFF (no API key found) - continuing without it.\n")

    print("Running latency benchmark against the real pipeline "
          "(live Ollama + real DB, fake user_id - no real user data touched)...\n")
    results = []
    for label, prompt, has_ctx in TEST_MESSAGES:
        print(f"Running: {label} ({prompt!r})...")
        results.append(run_one(label, prompt, has_ctx))
    print_report(results)


if __name__ == "__main__":
    main()
