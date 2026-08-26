"""
LangSmith evaluation for rag.py::retrieve_relevant_chunks_with_metadata -
the function that embeds a query (via Ollama's nomic-embed-text) and finds
the closest-matching knowledge-base chunks via pgvector cosine similarity.

Unlike safety/routing/memory, this is NOT a pure offline function: it makes
a real Ollama embedding call and a real database query per case. All cases
use a nonexistent user_id (999999) so retrieval only ever draws from the
global knowledge base (user_id IS NULL) - never a real person's private
chunks - keeping this reproducible and privacy-safe the same way the
memory-relevance eval's synthetic session_history did.

Ground truth design note: the first draft of this dataset used the
curated category name (e.g. "Sleep Hygiene") as the only acceptable source
for each query. Running it against the real knowledge base showed several
"failures" that turned out not to be failures at all - large ingested PDFs
(RewireYourBrainThinkYourWayToABetterLife2010.pdf,
Helping_the_Anxious_Teen_120620.pdf, DealingwithDistress.pdf,
therapists_guide_to_brief_cbtmanualsm.pdf) cover overlapping ground and
sometimes score higher than the curated chunk for the same topic. Reading
the actual winning chunk text confirmed these were genuinely on-topic, not
retrieval errors - so each case's ground truth is a small VERIFIED set of
acceptable sources, not one exact label. This mirrors the same "read the
real evidence before asserting the expected answer" discipline used for
the safety/routing/memory ground truth, just applied to a different kind
of evidence (chunk content instead of code logic).

Metrics:
  - top1_source_accuracy: does the top-ranked chunk come from one of the
    verified-acceptable sources for that query?
  - production_threshold_pass_rate: of the correctly-matched cases, does
    the similarity score actually clear the real production cutoff
    (pages.py::_filter_chunks_by_relevance, threshold=0.65)? A technically
    "correct" match that scores below this is silently dropped in the real
    app - the user gets NO knowledge-base content injected at all. This is
    the metric tied to an actual production behavior change, the same role
    crisis_recall/guardrail_trigger_recall played in the earlier evals.
  - distractor_rejection: for a query genuinely unrelated to mental health,
    does nothing clear the production threshold?
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from rag import retrieve_relevant_chunks_with_metadata  # noqa: E402

DATASET_NAME = "mindwell-rag-retrieval"
PRODUCTION_SIMILARITY_THRESHOLD = 0.65  # pages.py::_filter_chunks_by_relevance
FAKE_USER_ID = 999999  # never a real account - draws only from user_id IS NULL

CORE_CASE = "core"
DISTRACTOR_CASE = "distractor"
AMBIGUOUS_CASE = "ambiguous"

# Each case: (query, acceptable_sources, category, note)
CASES = [
    ("I keep having panic attacks and cant breathe",
     {"Anxiety and Panic Management"}, CORE_CASE, ""),
    ("can you walk me through a breathing exercise to calm down",
     {"Breathing Exercises", "DealingwithDistress.pdf"}, CORE_CASE,
     "verified: DealingwithDistress.pdf's top chunk is genuine relaxation/breathing content"),
    ("how do I challenge my negative automatic thoughts",
     {"CBT Techniques"}, CORE_CASE, ""),
    ("what are some healthy ways to cope with stress",
     {"Coping Strategies"}, CORE_CASE, ""),
    ("I am thinking about ending my life",
     {"Crisis Resources"}, CORE_CASE,
     "scores right at the production threshold boundary - see production_threshold_pass_rate"),
    ("I feel so hopeless and empty lately, nothing brings me joy anymore",
     {"Depression and Low Mood"}, CORE_CASE,
     "scores right at the production threshold boundary - see production_threshold_pass_rate"),
    ("I feel disconnected from reality, how do I ground myself",
     {"Grounding Techniques"}, CORE_CASE, ""),
    ("how can I practice being more present and mindful",
     {"Mindfulness"}, CORE_CASE, ""),
    ("I cant sleep, my mind wont stop racing at night",
     {"Sleep Hygiene", "RewireYourBrainThinkYourWayToABetterLife2010.pdf"}, CORE_CASE,
     "verified: the PDF's top chunk is genuine sleep-science content"),
    ("I am so overwhelmed with work stress, how do I manage it",
     {"Stress Management", "RewireYourBrainThinkYourWayToABetterLife2010.pdf"}, CORE_CASE,
     "verified: the PDF's top chunk is genuine stress/overwhelm content"),
    ("I feel restless and on edge all the time, like something bad is about to happen",
     {"Anxiety and Panic Management", "Helping_the_Anxious_Teen_120620.pdf"}, CORE_CASE,
     "adjacent-category check (anxiety phrased without the word 'anxiety') - "
     "verified: the PDF's top chunk is genuine anxiety/fear content"),

    # Genuinely ambiguous between two valid categories - documented, not
    # scored as pass/fail, same reasoning as the ambiguous cases in the
    # safety and routing evals.
    ("what techniques can help me deal with negative thinking patterns",
     {"CBT Techniques", "Coping Strategies", "therapists_guide_to_brief_cbtmanualsm.pdf"},
     AMBIGUOUS_CASE, "genuinely overlaps CBT and Coping Strategies - not a single right answer"),

    ("what is a good pizza topping combination",
     set(), DISTRACTOR_CASE, "unrelated to mental health - nothing should clear threshold"),
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
            "RAG retrieval eval for rag.py::retrieve_relevant_chunks_with_metadata. "
            "Source of truth is CASES in evaluations/rag_eval.py - this dataset "
            "is rebuilt from that list on every run. Requires live Ollama + DB."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"query": query} for query, _, _, _ in CASES],
        outputs=[
            {"acceptable_sources": sorted(sources), "category": category}
            for _, sources, category, _ in CASES
        ],
        metadata=[{"category": category, "note": note} for _, _, category, note in CASES],
    )
    return dataset


def target(inputs: dict) -> dict:
    chunks, metadata = retrieve_relevant_chunks_with_metadata(
        FAKE_USER_ID, inputs["query"], top_k=3
    )
    top = metadata[0] if metadata else None
    return {
        "top_source": top["source"] if top else None,
        "top_similarity_score": top["similarity_score"] if top else None,
    }


def exact_match_evaluator(run, example) -> dict:
    outputs = run.outputs or {}
    expected = example.outputs or {}
    acceptable = set(expected.get("acceptable_sources") or [])
    category = expected.get("category")
    top_source = outputs.get("top_source")

    if category == DISTRACTOR_CASE:
        score = outputs.get("top_similarity_score") is None or \
            outputs.get("top_similarity_score", 1.0) < PRODUCTION_SIMILARITY_THRESHOLD
    else:
        score = top_source in acceptable
    return {"key": "exact_match", "score": 1 if score else 0}


def rag_quality_summary(runs, examples) -> dict:
    core_total = core_correct = 0
    threshold_eligible = threshold_pass = 0
    distractor_total = distractor_correct = 0
    notes = []

    for run, example in zip(runs, examples):
        category = (example.metadata or {}).get("category", "")
        expected = example.outputs or {}
        acceptable = set(expected.get("acceptable_sources") or [])
        outputs = run.outputs or {}
        top_source = outputs.get("top_source")
        score = outputs.get("top_similarity_score")

        if category == CORE_CASE:
            core_total += 1
            matched = top_source in acceptable
            if matched:
                core_correct += 1
                threshold_eligible += 1
                if score is not None and score >= PRODUCTION_SIMILARITY_THRESHOLD:
                    threshold_pass += 1
                else:
                    notes.append(
                        f"[{category}] {example.inputs.get('query')!r} -> "
                        f"correct source ({top_source}) but score={score} < "
                        f"production threshold {PRODUCTION_SIMILARITY_THRESHOLD} "
                        f"- would be silently dropped in the real app"
                    )
            else:
                notes.append(
                    f"[{category}] {example.inputs.get('query')!r} -> "
                    f"top_source={top_source!r} not in acceptable={sorted(acceptable)}"
                )
        elif category == DISTRACTOR_CASE:
            distractor_total += 1
            rejected = score is None or score < PRODUCTION_SIMILARITY_THRESHOLD
            if rejected:
                distractor_correct += 1
            else:
                notes.append(
                    f"[{category}] {example.inputs.get('query')!r} -> "
                    f"unexpectedly cleared threshold: top_source={top_source!r} score={score}"
                )
        elif category == AMBIGUOUS_CASE:
            notes.append(
                f"[{category}] {example.inputs.get('query')!r} -> "
                f"top_source={top_source!r} score={score} (informational, not scored)"
            )

    accuracy = round(core_correct / core_total, 4) if core_total else None
    threshold_rate = (
        round(threshold_pass / threshold_eligible, 4) if threshold_eligible else None
    )
    distractor_rate = (
        round(distractor_correct / distractor_total, 4) if distractor_total else None
    )

    if notes:
        print("\nFindings:")
        for note in notes:
            print(f"  {note}")

    return {
        "results": [
            {"key": "top1_source_accuracy", "score": accuracy},
            {"key": "production_threshold_pass_rate", "score": threshold_rate},
            {"key": "distractor_rejection", "score": distractor_rate},
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
    print("Note: this eval calls real Ollama embeddings + a real DB per case, so it's slower than the others.")

    results = evaluate(
        target,
        data=dataset.name,
        evaluators=[exact_match_evaluator],
        summary_evaluators=[rag_quality_summary],
        experiment_prefix="rag-retrieval",
        client=client,
        description="Eval run for rag.py::retrieve_relevant_chunks_with_metadata",
        max_concurrency=2,
    )
    print(f"\nExperiment complete: {results.experiment_name}")


if __name__ == "__main__":
    main()
