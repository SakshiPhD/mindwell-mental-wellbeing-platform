"""
LangSmith evaluation for router_graph.py::route() - the classifier that picks
one of 8 intent labels (crisis, casual_greeting, continuity_followup,
coping_request, emotional_support, event_sharing, emotional_response,
general_chat) for every incoming message.

Same Dataset + Experiment pattern as evaluations/safety_crisis_eval.py, and
the same reasoning for why this is a different, complementary check to
tests/test_router_graph.py: that pytest file only proves the graph agrees
with the two retired routers it replaced ("did we break anything during the
rewrite"). It never asked "is the label actually correct" - two routers can
share the same bug and an equivalence test will never see it. This eval
assigns a real expected label to each case (many borrowed from that same
17-case list) and checks against that instead.

What "pass" means here is less binary than the safety eval, because a wrong
routing label degrades experience quality rather than creates danger - with
one exception: risk_hint="high" must ALWAYS produce intent_label="crisis",
no matter what the message text says. That's tracked as its own metric
(crisis_override_reliability, target 100%) separately from general
per-intent accuracy, the same way crisis_recall was kept separate from
false_positive_rate in the safety eval.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from router_graph import route  # noqa: E402

DATASET_NAME = "mindwell-routing-classification"

ALL_INTENTS = {
    "crisis", "casual_greeting", "continuity_followup", "coping_request",
    "emotional_support", "event_sharing", "emotional_response", "general_chat",
}

# Each case: (message, has_session_context, references_past, risk_hint,
#             expected_intent_label, category, note)
CASES = [
    # --- casual_greeting ---
    ("hi", False, False, "low", "casual_greeting", "core", ""),
    ("good morning", False, False, "low", "casual_greeting", "core", ""),

    # --- continuity_followup (from the existing 17-case equivalence list) ---
    ("do you have context what we were discussing?", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("do you have context what we were discussing till now", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("what did we talk about", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("we discussed my career stress earlier right?", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("what we have discussed so far?", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("did i mention my relocation", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("what did i tell you last time", True, False, "low",
     "continuity_followup", "core", "from tests/test_router_graph.py"),
    ("continue", True, False, "low",
     "continuity_followup", "core", "short-followup marker, needs session context"),
    ("continue", False, False, "low",
     "general_chat", "session_context_matters",
     "same word, but short-followup only triggers when has_session_context=True"),

    # --- coping_request ---
    ("can you suggest some breathing exercises to help me calm down", False, False, "low",
     "coping_request", "core", "from tests/test_router_graph.py"),
    ("what support can you give me?", False, False, "low",
     "coping_request", "core", "'give' is a coping keyword"),
    ("what techniques can help me manage panic attacks", False, False, "low",
     "coping_request", "core", ""),

    # --- emotional_support ---
    ("I've been really anxious about my exams and can't sleep well.", False, False, "low",
     "emotional_support", "core", "from tests/test_router_graph.py"),
    ("I feel so stressed and overwhelmed right now", False, False, "low",
     "emotional_support", "confusion_pair",
     "'stressed'/'overwhelmed' are in both EMOTIONAL_SUPPORT_KEYWORDS and "
     "EMOTION_WORDS, but emotional_support is checked first"),

    # --- emotional_response ---
    ("I feel so scared and lost right now", False, False, "low",
     "emotional_response", "confusion_pair",
     "'scared' is only in EMOTION_WORDS, not EMOTIONAL_SUPPORT_KEYWORDS - "
     "same kind of message as the emotional_support case above, different label"),
    ("I feel hurt and broken after that conversation", False, False, "low",
     "emotional_response", "core", ""),
    ("today I went to a funeral and I feel devastated", False, False, "low",
     "emotional_response", "confusion_pair",
     "has both an event marker ('today i', 'went to') and an emotion word "
     "('devastated') - emotion wins over event_sharing by design"),

    # --- event_sharing ---
    ("today i talked to my friend and her career is going great", False, False, "low",
     "event_sharing", "core", "from tests/test_router_graph.py"),
    ("today I visited my grandmother and it was lovely", False, False, "low",
     "event_sharing", "core", "event marker with no listed emotion word"),

    # --- general_chat ---
    ("what is the capital of France?", False, False, "low",
     "general_chat", "core", ""),
    ("why do you always ask repeated questions at the end of each sentence?", False, False, "low",
     "general_chat", "core",
     "the real false positive fixed in the safety eval - correctly low risk "
     "upstream, and correctly no coping/emotional keywords here either"),

    # --- crisis: the one non-negotiable case, risk_hint="high" must always win ---
    ("I dont want to live anymore", False, False, "high",
     "crisis", "crisis_override", "from tests/test_router_graph.py"),
    ("this is the end, I cant do this anymore, its decided, no going back", False, False, "high",
     "crisis", "crisis_override",
     "genuine extreme-crisis phrasing (see safety eval) - here tested with "
     "the risk_hint the safety layer would actually attach in production"),
    ("what a beautiful sunny day", False, False, "high",
     "crisis", "crisis_override",
     "deliberately unrelated, cheerful text - proves risk_hint overrides "
     "the message content entirely, not just crisis-shaped text"),

    # --- known findings: likely real bugs, included to be confirmed by the eval ---
    ("thanks, that helps", False, False, "low",
     "general_chat", "known_finding",
     "'help' is a coping keyword and matches as a substring of 'helps' - "
     "expect this to come back coping_request, which would be wrong: this "
     "is a closing/gratitude message, not a request for coping techniques"),

    # --- known limitation: not scored as a hard pass/fail target this milestone ---
    ("I am not feeling well today.", False, False, "low",
     "emotional_response", "known_limitation",
     "'not feeling well' isn't literally in any keyword list, so this likely "
     "falls through to general_chat - a real gap, but a broader one (keyword "
     "systems can't cover every phrasing) than this focused milestone's scope"),
]

CRISIS_OVERRIDE_CATEGORY = "crisis_override"
LIMITATION_CATEGORIES = {"known_limitation"}


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
            "Routing-classification eval for router_graph.py::route(). "
            "Source of truth is CASES in evaluations/routing_eval.py - "
            "this dataset is rebuilt from that list on every run."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            {
                "message": msg,
                "has_session_context": hsc,
                "references_past": rp,
                "risk_hint": rh,
            }
            for msg, hsc, rp, rh, _, _, _ in CASES
        ],
        outputs=[
            {"intent_label": expected, "category": category}
            for _, _, _, _, expected, category, _ in CASES
        ],
        metadata=[{"category": category, "note": note} for _, _, _, _, _, category, note in CASES],
    )
    return dataset


def target(inputs: dict) -> dict:
    result = route(
        inputs["message"],
        has_session_context=inputs["has_session_context"],
        references_past=inputs["references_past"],
        risk_hint=inputs["risk_hint"],
    )
    return {"intent_label": result["intent_label"]}


def exact_match_evaluator(run, example) -> dict:
    outputs = run.outputs or {}
    expected = example.outputs or {}
    correct = outputs.get("intent_label") == expected.get("intent_label")
    return {"key": "exact_match", "score": 1 if correct else 0}


def routing_accuracy_summary(runs, examples) -> dict:
    """
    Two numbers that matter more than overall accuracy:
      - crisis_override_reliability: of every case where risk_hint="high",
        did intent_label come back "crisis" every single time? Target 100%,
        same non-negotiable framing as crisis_recall in the safety eval.
      - per_intent_accuracy: accuracy broken out per expected label, so a
        weak category (e.g. emotional_response vs emotional_support
        confusion) can't hide behind a good overall average.
    known_limitation cases are excluded from per-intent accuracy and
    reported separately instead - same reasoning as the ambiguous cases in
    the safety eval: real gaps worth documenting, not this milestone's bar.
    """
    per_intent_total = {}
    per_intent_correct = {}
    crisis_override_total = 0
    crisis_override_correct = 0
    limitation_notes = []
    mismatches = []

    for run, example in zip(runs, examples):
        expected = (example.outputs or {}).get("intent_label")
        category = (example.metadata or {}).get("category", "")
        actual = (run.outputs or {}).get("intent_label")

        if category == CRISIS_OVERRIDE_CATEGORY:
            crisis_override_total += 1
            if actual == "crisis":
                crisis_override_correct += 1

        if category in LIMITATION_CATEGORIES:
            limitation_notes.append(
                f"[{category}] {example.inputs.get('message')!r} -> expected={expected!r} actual={actual!r}"
            )
            continue

        per_intent_total[expected] = per_intent_total.get(expected, 0) + 1
        if actual == expected:
            per_intent_correct[expected] = per_intent_correct.get(expected, 0) + 1
        else:
            mismatches.append(
                f"[{category}] {example.inputs.get('message')!r} -> expected={expected!r} actual={actual!r}"
            )

    crisis_reliability = (
        round(crisis_override_correct / crisis_override_total, 4)
        if crisis_override_total else None
    )

    results = [{"key": "crisis_override_reliability", "score": crisis_reliability}]
    for intent in sorted(ALL_INTENTS):
        total = per_intent_total.get(intent, 0)
        if total:
            acc = round(per_intent_correct.get(intent, 0) / total, 4)
            results.append({"key": f"accuracy_{intent}", "score": acc})

    if mismatches:
        print("\nMismatches (real findings, not known limitations):")
        for note in mismatches:
            print(f"  {note}")
    if limitation_notes:
        print("\nKnown limitations (not scored, documented gaps):")
        for note in limitation_notes:
            print(f"  {note}")

    return {"results": results}


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
        evaluators=[exact_match_evaluator],
        summary_evaluators=[routing_accuracy_summary],
        experiment_prefix="routing-classification",
        client=client,
        description="Eval run for router_graph.py::route()",
    )
    print(f"\nExperiment complete: {results.experiment_name}")


if __name__ == "__main__":
    main()
