"""
LangSmith evaluation for engine.py::MultiAgentEngine._build_relevant_memory_recall
- the function that decides which past session(s) are relevant enough to
surface for the current message. This is the function actually used in
production (3 call sites in run_care_pipeline); its near-identical sibling
_select_session_context is fully written but never called anywhere in the
app, so it's deliberately left out of this eval as dead code, not a gap.

Unlike safety/routing, there's no existing pytest coverage for this
function at all - this is its first dedicated test of any kind.

Retrieval here is plain keyword-overlap scoring against session summaries
(not semantic search), so the failure shape to look for is the same one
found in the safety and routing evals: a keyword matching as a bare
substring instead of a whole word. Checking the matching code directly
before writing this dataset found exactly that: "work" (from a query about
work stress) matches inside "...time working." in an unrelated
partner-conflict session's summary, pulling it in as falsely "relevant"
purely because of the substring collision - not because the two sessions
are actually related. Fixed as part of this same milestone with
word-boundary matching (same shape of fix as router_graph.py::_keyword_hit
and pages.py's extreme-crisis keyword narrowing).

Metrics:
  - relevance_recall: when a past session is clearly on-topic for the
    current message, does its summary actually get surfaced? Target 100% -
    missing this makes the app seem to have forgotten something real.
  - distractor_leakage_rate: does an UNRELATED session's summary also get
    pulled in alongside the correct one, purely from keyword collision?
    Target as close to 0% as possible - low-severity compared to a missed
    recall, but still noise that dilutes the context the Coach agent sees.
  - silence_correctness: when nothing is actually relevant, does the
    function correctly return nothing rather than force a stretch match?
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from engine import MultiAgentEngine  # noqa: E402

DATASET_NAME = "mindwell-memory-relevance-scoring"

RELEVANCE_CASE = "relevance_case"
SILENCE_CASE = "silence_case"

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
    {"session_id": "s3", "date": "2026-08-01", "tone": "calm",
     "summary": "User discussed enjoying painting as a way to relax on weekends.",
     "facts": {}},
]

# Each case: (user_input, min_score, allow_recent_fallback, expected_session_id
#             or None, forbidden_session_ids, category, note)
CASES = [
    ("I am so stressed about my deadlines at work again", 3, False,
     "s0", ["s1", "s2", "s3"], RELEVANCE_CASE,
     "found by this eval: 'work' matches inside 'working' in s1's unrelated "
     "partner-conflict summary, pulling it in as a false distractor"),
    ("things with my partner have been tense lately", 3, False,
     "s1", ["s0", "s2", "s3"], RELEVANCE_CASE, ""),
    ("I cant sleep at night and feel so exhausted", 3, False,
     "s2", ["s0", "s1", "s3"], RELEVANCE_CASE,
     "found by this eval: 'feel' matches inside 'feeling' in s0's unrelated "
     "work-stress summary, pulling it in as a false distractor"),
    ("painting has been such a relaxing hobby for me", 3, False,
     "s3", ["s0", "s1", "s2"], RELEVANCE_CASE, ""),
    ("what is the weather like today", 3, False,
     None, ["s0", "s1", "s2", "s3"], SILENCE_CASE,
     "nothing relevant - must return nothing, not a stretch match"),
]


def build_dataset(client):
    from langsmith.utils import LangSmithNotFoundError

    try:
        existing = client.read_dataset(dataset_name=DATASET_NAME)
        client.delete_dataset(dataset_id=existing.id)
    except LangSmithNotFoundError:
        pass

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "Memory-relevance-scoring eval for "
            "engine.py::_build_relevant_memory_recall. Source of truth is "
            "CASES/SESSION_HISTORY in evaluations/memory_relevance_eval.py - "
            "this dataset is rebuilt from that list on every run."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            {"user_input": text, "min_score": min_score, "allow_recent_fallback": fallback}
            for text, min_score, fallback, _, _, _, _ in CASES
        ],
        outputs=[
            {"expected_session_id": expected, "forbidden_session_ids": forbidden}
            for _, _, _, expected, forbidden, _, _ in CASES
        ],
        metadata=[{"category": category, "note": note} for _, _, _, _, _, category, note in CASES],
    )
    return dataset


_engine = MultiAgentEngine()
_SUMMARY_BY_ID = {s["session_id"]: s["summary"] for s in SESSION_HISTORY}


def target(inputs: dict) -> dict:
    result = _engine._build_relevant_memory_recall(
        inputs["user_input"],
        {"session_history": SESSION_HISTORY},
        min_score=inputs["min_score"],
        allow_recent_fallback=inputs["allow_recent_fallback"],
    )
    included = [sid for sid, summary in _SUMMARY_BY_ID.items() if summary in result]
    return {"recall_text": result, "included_session_ids": included}


def correctness_evaluator(run, example) -> dict:
    outputs = run.outputs or {}
    expected = example.outputs or {}
    included = set(outputs.get("included_session_ids") or [])
    expected_id = expected.get("expected_session_id")
    forbidden = set(expected.get("forbidden_session_ids") or [])

    if expected_id is None:
        correct = len(included) == 0
    else:
        correct = expected_id in included and not (included & forbidden)
    return {"key": "exact_match", "score": 1 if correct else 0}


def memory_relevance_summary(runs, examples) -> dict:
    relevance_total = relevance_recalled = 0
    relevance_with_leakage = 0
    silence_total = silence_correct = 0
    notes = []

    for run, example in zip(runs, examples):
        category = (example.metadata or {}).get("category", "")
        expected = example.outputs or {}
        included = set((run.outputs or {}).get("included_session_ids") or [])
        expected_id = expected.get("expected_session_id")
        forbidden = set(expected.get("forbidden_session_ids") or [])

        if category == RELEVANCE_CASE:
            relevance_total += 1
            recalled = expected_id in included
            leaked = bool(included & forbidden)
            if recalled:
                relevance_recalled += 1
            if leaked:
                relevance_with_leakage += 1
                notes.append(
                    f"[{category}] {example.inputs.get('user_input')!r} -> "
                    f"included={sorted(included)} forbidden_present={sorted(included & forbidden)}"
                )
        elif category == SILENCE_CASE:
            silence_total += 1
            if not included:
                silence_correct += 1
            else:
                notes.append(
                    f"[{category}] {example.inputs.get('user_input')!r} -> "
                    f"expected nothing, got included={sorted(included)}"
                )

    recall = round(relevance_recalled / relevance_total, 4) if relevance_total else None
    leakage_rate = round(relevance_with_leakage / relevance_total, 4) if relevance_total else None
    silence = round(silence_correct / silence_total, 4) if silence_total else None

    if notes:
        print("\nFindings:")
        for note in notes:
            print(f"  {note}")

    return {
        "results": [
            {"key": "relevance_recall", "score": recall},
            {"key": "distractor_leakage_rate", "score": leakage_rate},
            {"key": "silence_correctness", "score": silence},
        ]
    }


def main():
    from tracing import configure_tracing
    from langsmith import Client, evaluate

    active = configure_tracing(environment="development")
    if not active:
        print("LangSmith is not configured (no API key found) - aborting eval.")
        sys.exit(1)

    client = Client()
    dataset = build_dataset(client)
    print(f"Dataset '{DATASET_NAME}' rebuilt with {len(CASES)} cases.")

    results = evaluate(
        target,
        data=dataset.name,
        evaluators=[correctness_evaluator],
        summary_evaluators=[memory_relevance_summary],
        experiment_prefix="memory-relevance-scoring",
        client=client,
        description="Eval run for engine.py::_build_relevant_memory_recall",
    )
    print(f"\nExperiment complete: {results.experiment_name}")


if __name__ == "__main__":
    main()
