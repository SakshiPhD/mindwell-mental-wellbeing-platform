"""
LangSmith tracing configuration.

Deliberately opt-in and fail-open:
- Tracing only activates if a LangSmith API key is actually configured.
  No key configured -> the app behaves exactly as it did with no tracing
  code at all. This is the default, and stays the default until a real
  redaction/consent/retention policy exists for tracing real user data (see
  MINDWELL_PROJECT_CONTEXT_AND_LLMOPS_ROADMAP.md section 11) — until then,
  this must only ever be pointed at synthetic/test conversations, never a
  real account's conversation history.
- If LangSmith itself is misconfigured or unreachable, the app must keep
  working normally. LangChain's own tracing callbacks are designed to
  swallow upload failures rather than raise, but that's verified directly
  in tests/test_tracing_config.py rather than assumed.

Credentials resolve the same way DB credentials do (see
database.py::_load_db_credentials): a [langsmith] section in
.streamlit/secrets.toml read from a path anchored to this file (so it
works regardless of the directory the app was launched from), then plain
environment variables as a fallback. Never hardcoded, never committed.

Redaction of LangChain's/LangGraph's OWN automatic tracing:
Setting LANGCHAIN_TRACING_V2=true does not just enable the manual
`langsmith.trace()` spans this codebase adds explicitly (see
engine.py::_call_agent) - it also makes LangChain auto-instrument every
ChatOllama.invoke() call and every LangGraph node execution, uploading
their raw inputs/outputs (full prompts, full user messages) by default.
That auto-tracing resolves its default Client through three independent,
un-synchronized places in these libraries:
  1. langsmith.run_helpers._CLIENT      (a contextvars.ContextVar)
  2. langsmith.run_trees._CLIENT         (a plain module global - the
     fallback RunTree itself uses when no client is otherwise resolved)
  3. langchain_core.tracers.langchain._CLIENT  (a plain module global -
     what LangChainTracer actually uses to post ChatOllama/LangGraph
     auto-traces; this is the one confirmed to leak raw content)
None of them expose a supported "set the default" API, so
_install_redacted_default_client() reaches into all three directly and
points them at one Client(hide_inputs=True, hide_outputs=True) instance.
That's a deliberate, defensive choice over redacting content case-by-case:
it guarantees nothing raw leaves the process via ANY tracing path, known
or future, at the cost of losing the (already-synthetic-only,
already-non-sensitive) small metadata our own custom spans set as
inputs/outputs - verified in tests/test_tracing_config.py.
"""
import logging
import os

logger = logging.getLogger(__name__)

_configured = False


def _load_langsmith_config():
    """Return {"api_key": ..., "project": ..., "endpoint": ...} or None."""
    try:
        import toml
        here = os.path.dirname(os.path.abspath(__file__))
        secrets_path = os.path.abspath(os.path.join(here, "..", ".streamlit", "secrets.toml"))
        if os.path.isfile(secrets_path):
            with open(secrets_path, "r") as f:
                parsed = toml.load(f)
            ls = parsed.get("langsmith")
            if ls and ls.get("api_key"):
                return {
                    "api_key": ls["api_key"],
                    "project": ls.get("project", "mindwell-development"),
                    "endpoint": ls.get("endpoint", "https://api.smith.langchain.com"),
                }
    except Exception as e:
        logger.warning("Could not read LangSmith config from secrets.toml: %s", e)

    if os.getenv("LANGCHAIN_API_KEY"):
        return {
            "api_key": os.getenv("LANGCHAIN_API_KEY"),
            "project": os.getenv("LANGCHAIN_PROJECT", "mindwell-development"),
            "endpoint": os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
        }

    return None


def _install_redacted_default_client(config):
    """
    Force every default-client resolution path LangSmith/LangChain use for
    AUTOMATIC tracing (ChatOllama auto-instrumentation, LangGraph node
    traces - anything not going through our own explicit trace() spans) to
    resolve to one Client with hide_inputs/hide_outputs=True.

    Reaches into three separate modules' private globals because none of
    them expose a supported "set the process default client" API - see the
    module docstring above for why each one matters. If any of these
    imports/attributes ever change shape upstream, fail loudly rather than
    silently leaving raw content unredacted.
    """
    from langsmith import Client
    import langsmith.run_helpers as ls_run_helpers
    import langsmith.run_trees as ls_run_trees
    import langchain_core.tracers.langchain as lc_tracers_langchain

    redacting_client = Client(
        api_url=config["endpoint"],
        api_key=config["api_key"],
        hide_inputs=True,
        hide_outputs=True,
    )

    ls_run_helpers._CLIENT.set(redacting_client)
    ls_run_trees._CLIENT = redacting_client
    lc_tracers_langchain._CLIENT = redacting_client

    return redacting_client


def configure_tracing(environment: str = "development") -> bool:
    """
    Activate LangSmith tracing if (and only if) real credentials are
    configured. Returns True if tracing is now active, False otherwise —
    callers should not treat False as an error, just "not tracing right now".

    `environment` selects the project name suffix, keeping development and
    staging traces in separate LangSmith projects as the roadmap requires
    (section 11: "separate development and staging projects").
    """
    global _configured
    if _configured:
        return os.getenv("LANGCHAIN_TRACING_V2") == "true"

    config = _load_langsmith_config()
    if not config:
        logger.info("LangSmith tracing not configured (no API key found) — running untraced.")
        _configured = True
        return False

    project_base = config["project"]
    project_name = project_base if project_base.endswith(f"-{environment}") else f"{project_base}-{environment}"

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config["api_key"]
    os.environ["LANGCHAIN_PROJECT"] = project_name
    os.environ["LANGCHAIN_ENDPOINT"] = config["endpoint"]

    try:
        _install_redacted_default_client(config)
    except Exception as e:
        # Fail closed on tracing, not open: if we can't guarantee redaction,
        # do not let raw content start flowing to LangSmith at all.
        logger.error(
            "Could not install redacted LangSmith client (%s) - disabling "
            "tracing rather than risk uploading raw content.", e,
        )
        for var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"):
            os.environ.pop(var, None)
        _configured = True
        return False

    logger.info("LangSmith tracing enabled (redacted): project=%s", project_name)
    _configured = True
    return True


def tracing_active() -> bool:
    return os.getenv("LANGCHAIN_TRACING_V2") == "true"


def reset_for_testing():
    """
    Test-only: clear cached state so configure_tracing() re-evaluates.

    Also clears the three module globals _install_redacted_default_client()
    mutates - those live in third-party libraries and persist across tests
    in the same process otherwise, unlike this module's own _configured
    flag and the env vars.
    """
    global _configured
    _configured = False
    for var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"):
        os.environ.pop(var, None)

    try:
        import langsmith.run_helpers as ls_run_helpers
        import langsmith.run_trees as ls_run_trees
        import langchain_core.tracers.langchain as lc_tracers_langchain

        ls_run_helpers._CLIENT.set(None)
        ls_run_trees._CLIENT = None
        lc_tracers_langchain._CLIENT = None
    except Exception:
        pass
