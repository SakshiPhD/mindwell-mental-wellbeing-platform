"""
LangSmith evaluation for pages.py::_detect_extreme_crisis - the deterministic
(no LLM, pure keyword-matching) function that decides risk level
(low/medium/high) and whether a message counts as an "extreme crisis" (plan +
means + timeline + finality).

This is a real, re-runnable LangSmith Dataset + Experiment, not a one-off
script: run this file any time _detect_extreme_crisis changes, and it
rebuilds the dataset from CASES below (so the case list here in git is the
source of truth, not whatever happens to be in LangSmith already) and logs a
fresh experiment you can compare against previous runs in the LangSmith UI.

What "pass" means here is deliberately asymmetric, because the two failure
modes are not equally bad in a mental health app:
  - Missing a genuine crisis (false negative) is the worst possible failure.
    crisis_recall must be 1.0 - anything less is a hard fail on its own,
    regardless of other scores.
  - Flagging an everyday message as risky (false positive) is real but much
    less costly - it erodes trust and disrupts normal conversation (this is
    exactly the "the end" bug fixed earlier this project). Tracked as
    false_positive_rate, reported honestly rather than target-fit to zero.

Requires a configured LangSmith key (see tracing.py) - if tracing isn't
configured, this script exits early rather than silently doing nothing.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from pages import _detect_extreme_crisis  # noqa: E402

DATASET_NAME = "mindwell-safety-crisis-detection"

CRISIS_CATEGORIES = {"genuine_extreme_crisis", "genuine_high_risk"}
NON_CRISIS_CATEGORIES = {"false_positive_trap", "benign"}

# Each case: (message, expected_is_extreme, expected_risk, category, note)
# category drives the aggregate metrics below, not per-case pass/fail alone.
CASES = [
    # --- genuine_extreme_crisis: plan + means + timeline + finality ---
    (
        "this is the end, I cant do this anymore, its decided, no going back",
        True, "high", "genuine_extreme_crisis",
        "real case that motivated the original 'the end' keyword fix",
    ),
    (
        "I have a plan and everything I need, this is the end",
        True, "high", "genuine_extreme_crisis", "",
    ),
    (
        "I'm holding the pills right now, this is my last message to you",
        True, "high", "genuine_extreme_crisis", "",
    ),
    (
        "tonight i'm doing this, i have the rope, no going back",
        True, "high", "genuine_extreme_crisis", "",
    ),
    (
        "it's decided, no more talking, i already tried once and i know what works this time",
        True, "high", "genuine_extreme_crisis", "",
    ),
    (
        "don't try to stop me, i'm ready to act, this is final",
        True, "high", "genuine_extreme_crisis", "",
    ),
    (
        "everything i need is ready, it's happening tonight, this is my last conversation",
        True, "high", "genuine_extreme_crisis", "",
    ),

    # --- genuine_high_risk: real suicidal ideation, not (yet) extreme ---
    (
        "I want to die, I can't go on",
        False, "high", "genuine_high_risk",
        "2 high-risk keywords -> high per current logic, still not 'extreme'",
    ),
    (
        "I feel so hopeless and worthless lately",
        False, "high", "genuine_high_risk", "",
    ),
    (
        "I just want to end the pain, I can't continue like this",
        False, "high", "genuine_high_risk", "",
    ),
    (
        "nobody cares about me anymore",
        False, "medium", "genuine_high_risk",
        "single high-risk keyword -> medium, not high (existing pytest case)",
    ),
    (
        "I feel hopeless today",
        False, "medium", "genuine_high_risk", "",
    ),
    (
        "I don't think I can go on much longer",
        False, "medium", "genuine_high_risk", "",
    ),
    (
        "I feel like such a burden to everyone around me",
        False, "medium", "genuine_high_risk", "",
    ),

    # --- false_positive_trap: everyday phrasing containing risky substrings ---
    (
        "why do you always ask repeated questions at the end of each sentence?",
        False, "low", "false_positive_trap",
        "the exact real false positive that motivated the original fix",
    ),
    (
        "at the end of the day I just want to relax",
        False, "low", "false_positive_trap", "",
    ),
    (
        "can we talk at the end of the meeting?",
        False, "low", "false_positive_trap", "",
    ),
    (
        "No thanks, I don't need help with this assignment, I've got it covered.",
        False, "low", "false_positive_trap",
        "'don't need help' is a listed extreme keyword - newly discovered by this eval",
    ),
    (
        "I already tried the new restaurant downtown, it was great",
        False, "low", "false_positive_trap",
        "'already tried' is a listed extreme keyword - newly discovered by this eval",
    ),
    (
        "There's no more milk in the fridge, can you grab some?",
        False, "low", "false_positive_trap",
        "'no more' is a listed extreme keyword and a very common phrase - newly discovered",
    ),
    (
        "I'm completely done with this project, finally submitted it!",
        False, "low", "false_positive_trap",
        "'completely done' is a listed extreme keyword - newly discovered by this eval",
    ),

    # --- benign: plain everyday messages, nothing risky at all ---
    (
        "I had a great day today, thanks for asking!",
        False, "low", "benign", "",
    ),
    (
        "What's a good recipe for pasta?",
        False, "low", "benign", "",
    ),
    (
        "I'm feeling a bit tired today but okay overall",
        False, "low", "benign", "",
    ),
    (
        "Can you help me plan my week?",
        False, "low", "benign", "",
    ),
    (
        "I'm excited about my trip next month",
        False, "low", "benign", "",
    ),
    (
        "",
        False, "low", "benign", "empty message edge case",
    ),

    # --- ambiguous: known limitations of pure keyword matching, not scored
    #     as pass/fail against one "right" answer - reported separately so
    #     they don't distort the main recall/false-positive metrics.
    (
        "My friend told me she wants to end it all and I don't know what to do",
        False, "low", "ambiguous_third_person",
        "third-person risk report; keyword matching can't tell self vs. someone else",
    ),
    (
        "omg I'm dying 😂😂😂 that's hilarious",
        False, "low", "ambiguous_hyperbole",
        "casual hyperbole containing the literal high-risk phrase 'i'm dying'",
    ),
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
            "Safety/crisis-detection eval for pages.py::_detect_extreme_crisis. "
            "Source of truth is CASES in evaluations/safety_crisis_eval.py - "
            "this dataset is rebuilt from that list on every run."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[{"message": msg} for msg, *_ in CASES],
        outputs=[
            {"is_extreme": is_extreme, "risk": risk, "category": category}
            for _, is_extreme, risk, category, _ in CASES
        ],
        metadata=[{"category": category, "note": note} for _, _, _, category, note in CASES],
    )
    return dataset


def target(inputs: dict) -> dict:
    is_extreme, risk, flagged = _detect_extreme_crisis(inputs["message"])
    return {"is_extreme": is_extreme, "risk": risk, "flagged_keywords": flagged}


def exact_match_evaluator(run, example) -> dict:
    outputs = run.outputs or {}
    expected = example.outputs or {}
    correct = (
        outputs.get("is_extreme") == expected.get("is_extreme")
        and outputs.get("risk") == expected.get("risk")
    )
    return {"key": "exact_match", "score": 1 if correct else 0}


def crisis_recall_summary(runs, examples) -> dict:
    """
    The metric that actually matters: of every case that IS a genuine crisis
    (extreme or high-risk), did the function flag it as anything other than
    "low"? A single miss here is a hard fail, independent of every other
    number this eval reports.
    """
    crisis_total = 0
    crisis_caught = 0
    non_crisis_total = 0
    non_crisis_false_positive = 0
    ambiguous_notes = []

    for run, example in zip(runs, examples):
        category = (example.metadata or {}).get("category", "")
        outputs = run.outputs or {}
        actual_risk = outputs.get("risk", "low")

        if category in CRISIS_CATEGORIES:
            crisis_total += 1
            if actual_risk != "low":
                crisis_caught += 1
        elif category in NON_CRISIS_CATEGORIES:
            non_crisis_total += 1
            if actual_risk != "low":
                non_crisis_false_positive += 1
        else:
            ambiguous_notes.append(
                f"[{category}] {example.inputs.get('message')!r} -> risk={actual_risk!r}"
            )

    recall = round(crisis_caught / crisis_total, 4) if crisis_total else None
    fp_rate = round(non_crisis_false_positive / non_crisis_total, 4) if non_crisis_total else None

    if ambiguous_notes:
        print("\nAmbiguous cases (not scored, known limitations):")
        for note in ambiguous_notes:
            print(f"  {note}")

    return {
        "results": [
            {"key": "crisis_recall", "score": recall},
            {"key": "false_positive_rate", "score": fp_rate},
        ]
    }


def main():
    from tracing import configure_tracing
    from langsmith import Client, evaluate

    active = configure_tracing(environment="development")
    if not active:
        print("LangSmith is not configured (no API key found) - aborting eval.")
        print("This eval needs a real LangSmith project to log results to; "
              "see .streamlit/secrets.toml.example's [langsmith] section.")
        sys.exit(1)

    client = Client()
    dataset = build_dataset(client)
    print(f"Dataset '{DATASET_NAME}' rebuilt with {len(CASES)} cases.")

    results = evaluate(
        target,
        data=dataset.name,
        evaluators=[exact_match_evaluator],
        summary_evaluators=[crisis_recall_summary],
        experiment_prefix="safety-crisis-detection",
        client=client,
        description="Eval run for pages.py::_detect_extreme_crisis",
    )
    print(f"\nExperiment complete: {results.experiment_name}")


if __name__ == "__main__":
    main()
