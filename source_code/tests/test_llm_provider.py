"""
Tests for llm_provider.py's deterministic logic — circuit breaker state,
model-fallback candidate selection, and config parsing. These don't need a
real Ollama connection (kept fast and non-flaky, same philosophy as the rest
of the suite); the actual ChatOllama call path was verified by hand against
a live Ollama instance as part of the LangChain migration experiment
(baseline latency comparison, a forced-fallback test, and a forced
connection-failure test — see the milestone notes), not re-mocked here.
"""
import time
import llm_provider
from llm_provider import LLMProvider, _ends_cleanly, _to_bool, _env_int, _env_bool


def setup_function():
    """Circuit breaker state is module-level — reset between tests."""
    llm_provider._failure_history.clear()
    llm_provider._circuit_open_until.clear()


def test_circuit_breaker_opens_after_threshold_failures():
    model = "test-model-a"
    assert LLMProvider._can_call_model(model) is True
    for _ in range(llm_provider.CB_FAILURE_THRESHOLD):
        LLMProvider._record_failure(model)
    assert LLMProvider._can_call_model(model) is False


def test_circuit_breaker_recovers_on_success():
    model = "test-model-b"
    for _ in range(llm_provider.CB_FAILURE_THRESHOLD):
        LLMProvider._record_failure(model)
    assert LLMProvider._can_call_model(model) is False
    LLMProvider._record_success(model)
    assert LLMProvider._can_call_model(model) is True


def test_circuit_breaker_failures_outside_window_dont_count():
    model = "test-model-c"
    now = time.time()
    # Simulate failures from long before the failure window — should not
    # count toward opening the breaker.
    llm_provider._failure_history[model] = [now - llm_provider.CB_FAILURE_WINDOW_SECONDS - 10] * 10
    assert LLMProvider._can_call_model(model) is True


def test_fallback_candidates_includes_configured_models():
    candidates = LLMProvider._fallback_candidates(["primary-model"])
    assert "primary-model" in candidates
    assert llm_provider.AVAILABLE_MODELS["quality"] in candidates


def test_fallback_candidates_expands_llama3_aliases():
    candidates = LLMProvider._fallback_candidates(["llama3"])
    assert "llama3:latest" in candidates


def test_fallback_candidates_deduplicates():
    candidates = LLMProvider._fallback_candidates(["llama3:latest", "llama3:latest"])
    assert candidates.count("llama3:latest") == 1


def test_pick_best_available_returns_first_installed_match():
    installed = {"gemma2:2b", "llama3:latest"}
    picked = LLMProvider._pick_best_available(["llama3:latest", "gemma2:2b"], installed)
    assert picked == "llama3:latest"


def test_pick_best_available_returns_none_if_nothing_installed():
    # _pick_best_available always also considers the global AVAILABLE_MODELS
    # defaults, not just `preferred` — so "nothing installed" here means an
    # installed set that doesn't overlap those defaults either.
    picked = LLMProvider._pick_best_available(["nonexistent-model"], {"some-other-model:latest"})
    assert picked is None


def test_pick_best_available_respects_avoid_set():
    installed = {"llama3:latest", "gemma2:2b"}
    picked = LLMProvider._pick_best_available(["llama3:latest", "gemma2:2b"], installed, avoid={"llama3:latest"})
    assert picked == "gemma2:2b"


def test_ends_cleanly_true_for_complete_sentence():
    assert _ends_cleanly("This is a complete sentence.") is True
    assert _ends_cleanly("Is this a question?") is True


def test_ends_cleanly_false_for_truncated_text():
    assert _ends_cleanly("This sentence just cuts off in the") is False
    assert _ends_cleanly("Here's a list: 1. First thing, 2. Second,") is False


def test_ends_cleanly_false_for_empty():
    assert _ends_cleanly("") is False
    assert _ends_cleanly(None) is False


def test_to_bool_handles_common_representations():
    assert _to_bool("true") is True
    assert _to_bool("YES") is True
    assert _to_bool("1") is True
    assert _to_bool("false") is False
    assert _to_bool("no") is False
    assert _to_bool(None, default=True) is True


def test_env_int_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("TEST_ENV_INT", "not-a-number")
    assert _env_int("TEST_ENV_INT", 42) == 42
    monkeypatch.setenv("TEST_ENV_INT", "17")
    assert _env_int("TEST_ENV_INT", 42) == 17


def test_env_bool_reads_env_var(monkeypatch):
    monkeypatch.setenv("TEST_ENV_BOOL", "true")
    assert _env_bool("TEST_ENV_BOOL", False) is True
    monkeypatch.delenv("TEST_ENV_BOOL", raising=False)
    assert _env_bool("TEST_ENV_BOOL", False) is False
