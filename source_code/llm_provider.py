"""
LLM Provider Abstraction Layer
===============================
The actual model call goes through LangChain's ChatOllama (langchain-ollama)
instead of a hand-rolled HTTP client — same public interface
(LLMProvider.call_llm), same circuit breaker / retry / model-fallback logic,
now behind a swappable model-provider layer instead of one hard-coded to
Ollama specifically. Health-check/model-discovery endpoints (/api/version,
/api/tags) still use plain requests — they're simple GETs unrelated to the
actual chat completion, no reason to bring LangChain into that path too.
"""

import logging
import os
import random
import threading
import time
from typing import Dict, Any

import requests
import httpx
import ollama
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _to_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ends_cleanly(text: str) -> bool:
    """Heuristic for whether a non-streamed reply looks complete."""
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if stripped.endswith(("...", "…", ",", ";", ":", "-", "(", "[", "{", "/")):
        return False
    return stripped[-1] in '.!?"\')]}'


# ===================== CONFIGURATION =====================
LLM_PROVIDER = "ollama"

# Llama 3 defaults (override with env vars if needed)
AVAILABLE_MODELS = {
    "fast": os.getenv("OLLAMA_FAST_MODEL", "llama3:latest"),
    "quality": os.getenv("OLLAMA_QUALITY_MODEL", "llama3:latest"),
    "fallback": os.getenv("OLLAMA_FALLBACK_MODEL", "llama3:latest"),
}

OLLAMA_CONFIG = {
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    "model": AVAILABLE_MODELS["fast"],
}

AGENT_CONFIG = {
    "safety": {
        "temperature": 0.2,
        "num_predict": 96,
        "num_ctx": 2048,
        "model": AVAILABLE_MODELS["fast"],
        "json_output": True,
        "timeout_seconds": 30,   # small output — 30s enough
        "max_retries": 1,
    },
    "memory": {
        "temperature": 0.25,
        "num_predict": 180,      # reduced from 220 — memory summaries don't need long output
        "num_ctx": 2048,         # reduced from 4096 — smaller ctx = faster llama3 inference
        "model": AVAILABLE_MODELS["quality"],
        "json_output": True,
        "timeout_seconds": 110,  # llama3 on local hardware needs this
        "max_retries": 0,        # one clean long attempt — retrying doubles the wait
    },
    "orchestrator": {
        "temperature": 0.5,
        "num_predict": 260,
        "num_ctx": 3072,         # reduced from 4096 — trim_context already caps at 4800 chars
        "model": AVAILABLE_MODELS["quality"],
        "timeout_seconds": 130,  # orchestrator is the critical agent — give it most time
        "max_retries": 0,
    },
    "coach": {
        "temperature": 0.45,
        # 220 + max_retries=1 (the previous setting) was measured by
        # evaluations/latency_benchmark.py to roughly double latency on
        # long-answer intents (coping_request especially, per the coach
        # prompt's own "3-5 compact bullets" instruction) when it hit the
        # length limit - and the retry, capped at 260 by a hardcoded ceiling
        # in _call_ollama's recovery logic, still didn't reliably avoid
        # truncation. Same principle already used for "memory" below
        # ("one clean long attempt — retrying doubles the wait"), applied
        # here too: raised to 360 (empirically found - 3 representative
        # long-answer prompts all completed cleanly at 360, single attempt,
        # worst case ~19s vs. the previous two-attempt worst case ~58s that
        # still truncated) and max_retries dropped to 0 to eliminate the
        # double-latency risk entirely rather than trying to recover after
        # the fact.
        "num_predict": 360,
        "num_ctx": 2048,         # reduced from 3072
        "model": AVAILABLE_MODELS["quality"],
        "timeout_seconds": 110,
        "max_retries": 0,
    },
}

CB_FAILURE_WINDOW_SECONDS = _env_int("OLLAMA_CB_WINDOW_SECONDS", 60)
CB_OPEN_SECONDS = _env_int("OLLAMA_CB_OPEN_SECONDS", 30)
CB_FAILURE_THRESHOLD = _env_int("OLLAMA_CB_FAILURE_THRESHOLD", 3)
OLLAMA_MAX_CONCURRENT_REQUESTS = max(1, _env_int("OLLAMA_MAX_CONCURRENT_REQUESTS", 1))
OLLAMA_SWITCH_ON_TIMEOUT = _env_bool("OLLAMA_SWITCH_ON_TIMEOUT", False)
OLLAMA_UNAVAILABLE_COOLDOWN_SECONDS = max(3, _env_int("OLLAMA_UNAVAILABLE_COOLDOWN_SECONDS", 10))
OLLAMA_HEALTHCHECK_TIMEOUT_SECONDS = max(1, _env_int("OLLAMA_HEALTHCHECK_TIMEOUT_SECONDS", 2))

_failure_history = {}      # model -> [timestamps]
_circuit_open_until = {}   # model -> epoch seconds
_circuit_lock = threading.Lock()
_models_cache = {"ts": 0.0, "names": set()}
_ollama_request_gate = threading.Semaphore(OLLAMA_MAX_CONCURRENT_REQUESTS)
_service_health = {"available": True, "checked_at": 0.0, "last_log_at": 0.0}


class LLMProvider:
    """Factory class for calling LLMs."""

    @staticmethod
    def call_llm(agent_type: str, system_prompt: str, user_input: str) -> str:
        """Call an LLM with the configured backend."""
        try:
            config = AGENT_CONFIG.get(agent_type, AGENT_CONFIG["orchestrator"])
            if LLM_PROVIDER == "ollama":
                return LLMProvider._call_ollama(system_prompt, user_input, config)
            logger.error("Unknown LLM provider: %s", LLM_PROVIDER)
            return ""
        except Exception as e:
            logger.error("LLM call failed for agent '%s': %s", agent_type, e)
            return ""

    @staticmethod
    def _can_call_model(model: str) -> bool:
        now = time.time()
        with _circuit_lock:
            open_until = _circuit_open_until.get(model, 0)
            if now < open_until:
                return False

            history = [ts for ts in _failure_history.get(model, []) if now - ts <= CB_FAILURE_WINDOW_SECONDS]
            _failure_history[model] = history
            if len(history) >= CB_FAILURE_THRESHOLD:
                _circuit_open_until[model] = now + CB_OPEN_SECONDS
                return False
            return True

    @staticmethod
    def _record_failure(model: str):
        now = time.time()
        with _circuit_lock:
            history = [ts for ts in _failure_history.get(model, []) if now - ts <= CB_FAILURE_WINDOW_SECONDS]
            history.append(now)
            _failure_history[model] = history
            if len(history) >= CB_FAILURE_THRESHOLD:
                _circuit_open_until[model] = now + CB_OPEN_SECONDS

    @staticmethod
    def _record_success(model: str):
        with _circuit_lock:
            _failure_history[model] = []
            _circuit_open_until[model] = 0

    @staticmethod
    def _backoff_sleep(attempt: int):
        delay = min(0.3 * (2 ** attempt), 5.0) + random.uniform(0, 0.3)
        time.sleep(delay)

    @staticmethod
    def _mark_service_unavailable():
        with _circuit_lock:
            _service_health["available"] = False
            _service_health["checked_at"] = time.time()

    @staticmethod
    def _service_is_available(base_url: str, force: bool = False):
        now = time.time()
        with _circuit_lock:
            recently_checked = (now - _service_health.get("checked_at", 0.0)) < OLLAMA_UNAVAILABLE_COOLDOWN_SECONDS
            if not force and recently_checked and not _service_health.get("available", True):
                return False

        health_url = base_url.rstrip("/")
        if health_url.endswith("/api"):
            health_url = health_url[:-4]
        health_url = f"{health_url}/api/version"

        should_log = False
        try:
            resp = requests.get(health_url, timeout=OLLAMA_HEALTHCHECK_TIMEOUT_SECONDS)
            resp.raise_for_status()
            with _circuit_lock:
                _service_health["available"] = True
                _service_health["checked_at"] = now
            return True
        except Exception as err:
            with _circuit_lock:
                _service_health["available"] = False
                _service_health["checked_at"] = now
                if (now - _service_health.get("last_log_at", 0.0)) >= OLLAMA_UNAVAILABLE_COOLDOWN_SECONDS:
                    _service_health["last_log_at"] = now
                    should_log = True
            if should_log:
                logger.error("Ollama unavailable at %s: %s", base_url, err)
            return False

    @staticmethod
    def _fetch_installed_models(base_url: str, force: bool = False):
        now = time.time()
        if not force and _models_cache["names"] and (now - _models_cache["ts"] < 60):
            return set(_models_cache["names"])
        try:
            tags_url = base_url.rstrip("/")
            if tags_url.endswith("/api"):
                tags_url = tags_url[:-4]
            tags_url = f"{tags_url}/api/tags"
            r = requests.get(tags_url, timeout=8)
            r.raise_for_status()
            payload = r.json() or {}
            names = {str(m.get("name")) for m in payload.get("models", []) if m.get("name")}
            _models_cache["ts"] = now
            _models_cache["names"] = set(names)
            with _circuit_lock:
                _service_health["available"] = True
                _service_health["checked_at"] = now
            return names
        except Exception:
            with _circuit_lock:
                _service_health["available"] = False
                _service_health["checked_at"] = now
            return set(_models_cache["names"])

    @staticmethod
    def _pick_best_available(preferred, installed_models, avoid=None):
        avoid = avoid or set()
        candidates = LLMProvider._fallback_candidates(preferred or [])
        seen = set()
        for name in candidates:
            if not name or name in seen or name in avoid:
                continue
            seen.add(name)
            if name in installed_models:
                return name
        return None

    @staticmethod
    def _fallback_candidates(preferred=None):
        candidates = []
        candidates.extend(preferred or [])
        candidates.extend([
            AVAILABLE_MODELS.get("quality"),
            AVAILABLE_MODELS.get("fast"),
            AVAILABLE_MODELS.get("fallback"),
            "llama3:latest",
            "llama3:8b",
            "llama3.2:3b",
            "gemma2:2b",
            "gemma3:1b",
        ])

        # Expand common model aliases so explicit tags like llama3.2:3b can
        # gracefully fall back to locally-installed llama3 variants.
        expanded = []
        for raw in candidates:
            if not raw:
                continue
            name = str(raw).strip()
            if not name:
                continue
            expanded.append(name)
            low = name.lower()
            if low == "llama3":
                expanded.append("llama3:latest")
            if low.startswith("llama3.2:"):
                expanded.extend(["llama3:latest", "llama3:8b", "llama3"])
            if low == "llama3:latest":
                expanded.append("llama3")

        seen = set()
        ordered = []
        for name in expanded:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        return ordered

    @staticmethod
    def _pick_fallback_without_inventory(preferred=None, avoid=None):
        avoid = avoid or set()
        candidates = LLMProvider._fallback_candidates(preferred or [])

        # Prefer models that are not currently in circuit-breaker cooldown.
        for name in candidates:
            if name in avoid:
                continue
            if LLMProvider._can_call_model(name):
                return name

        # If all candidates are in cooldown, still return one so caller can try.
        for name in candidates:
            if name not in avoid:
                return name
        return None

    @staticmethod
    def _pick_memory_safe_model(installed_models, avoid=None):
        avoid = avoid or set()
        for name in ["gemma2:2b", "gemma3:1b", "llama3.2:1b", "llama3.2:3b", "llama3:latest"]:
            if name in installed_models and name not in avoid:
                return name
        return None

    @staticmethod
    def _call_ollama(system_prompt: str, user_input: str, config: Dict[str, Any]) -> str:
        """Output-only call to Ollama API with retries and circuit breaker."""
        base = OLLAMA_CONFIG["base_url"].rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        url = f"{base}/api/chat"
        if not LLMProvider._service_is_available(base):
            return ""

        model = config.get("model", OLLAMA_CONFIG["model"])
        fallback_model = AVAILABLE_MODELS.get("fallback") or OLLAMA_CONFIG["model"]

        try:
            timeout_seconds = int(config.get("timeout_seconds", 25))
        except (TypeError, ValueError):
            timeout_seconds = 25
        timeout_seconds = max(5, timeout_seconds)

        try:
            max_retries = int(config.get("max_retries", 1))
        except (TypeError, ValueError):
            max_retries = 1
        max_retries = max(0, max_retries)
        max_attempts = max_retries + 1

        # Timeout-driven model switches are opt-in because they can cause
        # expensive model swaps on local Ollama and worsen latency.
        allow_timeout_model_fallback = _to_bool(
            config.get("timeout_model_fallback"),
            default=OLLAMA_SWITCH_ON_TIMEOUT,
        )
        try:
            base_num_predict = int(config.get("num_predict", 220))
        except (TypeError, ValueError):
            base_num_predict = 220
        base_num_predict = max(32, base_num_predict)

        temperature = config.get("temperature", 0.7)
        num_ctx = config.get("num_ctx", 2048)  # reduced from 4096 — smaller ctx = faster llama3 inference
        json_output = bool(config.get("json_output"))
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_input)]

        installed = LLMProvider._fetch_installed_models(base)
        current_model = model
        tried_models = {current_model}
        if installed and current_model not in installed:
            picked = LLMProvider._pick_best_available([current_model, fallback_model], installed)
            if picked:
                logger.warning("Model '%s' not installed. Using '%s'.", current_model, picked)
                current_model = picked
                tried_models.add(current_model)
        elif not installed:
            # If model inventory lookup fails, still try safe known alternatives.
            picked = LLMProvider._pick_fallback_without_inventory(
                [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                avoid=tried_models,
            )
            if picked and picked != current_model:
                logger.warning(
                    "Could not read installed models. Trying '%s' instead of '%s'.",
                    picked, current_model,
                )
                current_model = picked
                tried_models.add(current_model)
        used_fallback = False

        if not LLMProvider._can_call_model(current_model):
            alt = None
            if installed:
                alt = LLMProvider._pick_best_available(
                    [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                    installed,
                    avoid=tried_models,
                )
            if not alt:
                alt = LLMProvider._pick_fallback_without_inventory(
                    [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                    avoid=tried_models,
                )
            if alt and alt != current_model:
                logger.warning(
                    "CircuitBreaker: Model '%s' is in cooldown. Trying '%s'.",
                    current_model, alt,
                )
                current_model = alt
                tried_models.add(current_model)
            else:
                logger.warning("CircuitBreaker: Model '%s' is in cooldown, skipping.", current_model)
                return ""

        current_num_predict = base_num_predict

        for attempt in range(max_attempts):
            try:
                # Keep retries adaptive: slightly reduce generation length and
                # allow more time after the first attempt for cold starts.
                request_timeout = min(timeout_seconds + (attempt * 12), max(timeout_seconds, 120))
                llm = ChatOllama(
                    model=current_model,
                    base_url=base,
                    temperature=temperature,
                    num_predict=current_num_predict,
                    num_ctx=num_ctx,
                    keep_alive="30m",
                    format="json" if json_output else "",
                    client_kwargs={"timeout": request_timeout},
                )
                with _ollama_request_gate:
                    response = llm.invoke(messages)
                LLMProvider._record_success(current_model)
                content = str(response.content or "")
                done_reason = str(response.response_metadata.get("done_reason", "") or "").strip().lower()

                if done_reason in {"length", "max_tokens"}:
                    logger.warning(
                        "LLM output hit length limit: model=%s attempt=%d/%d num_predict=%d content_len=%d",
                        current_model, attempt + 1, max_attempts, current_num_predict, len(content),
                    )
                    if attempt < max_attempts - 1:
                        # Keep the recovery modest: one concise completion retry,
                        # not a broad expansion into a much longer answer.
                        current_num_predict = min(base_num_predict + 60, 260)
                        continue

                if content and not _ends_cleanly(content):
                    logger.warning(
                        "LLM reply may be incomplete: model=%s done_reason=%s content_len=%d",
                        current_model, done_reason or "unknown", len(content),
                    )

                return content
            except httpx.TimeoutException:
                logger.warning("LLM Timeout: model=%s attempt=%d/%d", current_model, attempt + 1, max_attempts)
                LLMProvider._record_failure(current_model)
                if allow_timeout_model_fallback and not used_fallback:
                    installed = LLMProvider._fetch_installed_models(base, force=True)
                    alt = LLMProvider._pick_best_available(
                        [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                        installed,
                        avoid=tried_models,
                    )
                    if not alt:
                        alt = LLMProvider._pick_fallback_without_inventory(
                            [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                            avoid=tried_models,
                        )
                    if alt and alt != current_model:
                        current_model = alt
                        tried_models.add(current_model)
                        used_fallback = True
                        logger.warning("Model fallback: switched to '%s' after timeout.", alt)
                        continue
                if attempt < max_attempts - 1:
                    current_num_predict = max(80, int(current_num_predict * 0.8))
                    LLMProvider._backoff_sleep(attempt)
                else:
                    return ""
            except ollama.ResponseError as e:
                status_code = e.status_code if e.status_code and e.status_code > 0 else "unknown"
                detail = str(e.error or "").strip()[:220] or str(e)
                logger.error(
                    "LLM HTTP Error: status=%s model=%s attempt=%d/%d detail=%s",
                    status_code, current_model, attempt + 1, max_attempts, detail,
                )
                LLMProvider._record_failure(current_model)

                detail_lower = (detail or "").lower()
                if (
                    isinstance(status_code, int)
                    and status_code >= 500
                    and not used_fallback
                ):
                    installed = LLMProvider._fetch_installed_models(base, force=True)
                    alt = LLMProvider._pick_best_available(
                        [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                        installed,
                        avoid=tried_models,
                    )
                    if not alt:
                        alt = LLMProvider._pick_fallback_without_inventory(
                            [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                            avoid=tried_models,
                        )
                    if alt:
                        current_model = alt
                        tried_models.add(current_model)
                        used_fallback = True
                        logger.warning("Model fallback: switched to '%s' after server error.", alt)
                        continue

                # Model not found -> pick an installed one automatically.
                if isinstance(status_code, int) and status_code == 404:
                    installed = LLMProvider._fetch_installed_models(base, force=True)
                    alt = LLMProvider._pick_best_available(
                        [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                        installed,
                        avoid=tried_models,
                    )
                    if not alt:
                        alt = LLMProvider._pick_fallback_without_inventory(
                            [fallback_model, AVAILABLE_MODELS.get("quality"), AVAILABLE_MODELS.get("fast")],
                            avoid=tried_models,
                        )
                    if alt:
                        current_model = alt
                        tried_models.add(current_model)
                        used_fallback = True
                        logger.warning("Model fallback: switched to installed model '%s' after 404.", alt)
                        continue

                # Insufficient RAM -> downgrade to lighter installed model.
                if "requires more system memory" in detail_lower:
                    installed = LLMProvider._fetch_installed_models(base, force=True)
                    alt = LLMProvider._pick_memory_safe_model(installed, avoid=tried_models)
                    if not alt:
                        alt = LLMProvider._pick_fallback_without_inventory(
                            ["gemma2:2b", "gemma3:1b", fallback_model],
                            avoid=tried_models,
                        )
                    if alt:
                        current_model = alt
                        tried_models.add(current_model)
                        used_fallback = True
                        logger.warning("Memory fallback: switched to '%s' due to memory pressure.", alt)
                        continue

                if attempt < max_attempts - 1:
                    LLMProvider._backoff_sleep(attempt)
                else:
                    return ""
            except (ConnectionError, ollama.RequestError, httpx.HTTPError) as e:
                logger.error(
                    "LLM Request Error: model=%s attempt=%d/%d error=%s",
                    current_model, attempt + 1, max_attempts, e,
                )
                if isinstance(e, ConnectionError):
                    LLMProvider._mark_service_unavailable()
                LLMProvider._record_failure(current_model)
                if attempt < max_attempts - 1:
                    LLMProvider._backoff_sleep(attempt)
                else:
                    return ""
            except Exception as e:
                logger.error("LLM Processing Error: model=%s error=%s", current_model, e)
                LLMProvider._record_failure(current_model)
                return ""

        return ""
