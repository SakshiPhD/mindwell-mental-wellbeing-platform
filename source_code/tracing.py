"""
LangSmith tracing configuration.

Deliberately opt-in and fail-open:
- Tracing only activates if a LangSmith API key is actually configured.
  No key configured -> the app behaves exactly as it did with no tracing
  code at all.
- If LangSmith itself is misconfigured or unreachable, the app must keep
  working normally. LangChain's own tracing callbacks are designed to
  swallow upload failures rather than raise, but that's verified directly
  in tests/test_tracing_config.py rather than assumed.

Credentials resolve the same way DB credentials do (see
database.py::_load_db_credentials): a [langsmith] section in
.streamlit/secrets.toml read from a path anchored to this file (so it
works regardless of the directory the app was launched from), then plain
environment variables as a fallback. Never hardcoded, never committed.

Content policy (2026-08-25): the project owner is the sole user of this
app's real account (user_id=1) and explicitly authorized tracing that
account's real conversations with full content, precisely so LangSmith
traces are actually useful for debugging coaching quality, memory recall,
and routing decisions - not just timing. Content is therefore NOT redacted
by default. Before this decision, the earlier version of this module
forced hide_inputs=True/hide_outputs=True on every trace after a real
leak was found in LangChain's own auto-instrumentation (see git history /
MINDWELL_PROJECT_CONTEXT_AND_LLMOPS_ROADMAP.md section 11 for that
incident). If this app ever traces a second, real, non-owner user's
conversations, that blanket-consent basis no longer holds and redaction
(or per-user opt-in) must be revisited before tracing them.

Default-client plumbing:
Setting LANGCHAIN_TRACING_V2=true does not just enable the manual
`langsmith.trace()` spans this codebase adds explicitly (see
engine.py::_call_agent) - it also makes LangChain auto-instrument every
ChatOllama.invoke() call and every LangGraph node execution. That
auto-tracing resolves its default Client through three independent,
un-synchronized places in these libraries:
  1. langsmith.run_helpers._CLIENT      (a contextvars.ContextVar)
  2. langsmith.run_trees._CLIENT         (a plain module global - the
     fallback RunTree itself uses when no client is otherwise resolved)
  3. langchain_core.tracers.langchain._CLIENT  (a plain module global -
     what LangChainTracer actually uses to post ChatOllama/LangGraph
     auto-traces)
None of them expose a supported "set the default" API, so
_install_default_tracing_client() reaches into all three directly and
points them at one explicitly-configured Client instance, so there's a
single source of truth for how tracing behaves rather than three
independently-defaulting clients. hide_inputs/hide_outputs stay available
as constructor args here specifically so redaction can be turned back on
in one place if the content policy above ever changes.
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


def _install_default_tracing_client(config):
    """
    Force every default-client resolution path LangSmith/LangChain use for
    AUTOMATIC tracing (ChatOllama auto-instrumentation, LangGraph node
    traces - anything not going through our own explicit trace() spans) to
    resolve to one explicitly-constructed Client, instead of three
    independently-lazily-created ones.

    Content is NOT redacted here (hide_inputs/hide_outputs left at their
    default of None) - see the module docstring's "Content policy" section
    for why, and flip them back to True here if that policy changes.

    Reaches into three separate modules' private globals because none of
    them expose a supported "set the process default client" API - see the
    module docstring above for why each one matters.
    """
    from langsmith import Client
    import langsmith.run_helpers as ls_run_helpers
    import langsmith.run_trees as ls_run_trees
    import langchain_core.tracers.langchain as lc_tracers_langchain

    client = Client(
        api_url=config["endpoint"],
        api_key=config["api_key"],
    )

    ls_run_helpers._CLIENT.set(client)
    ls_run_trees._CLIENT = client
    lc_tracers_langchain._CLIENT = client

    return client


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
        _install_default_tracing_client(config)
    except Exception as e:
        logger.error(
            "Could not install the default LangSmith client (%s) - "
            "disabling tracing.", e,
        )
        for var in ("LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"):
            os.environ.pop(var, None)
        _configured = True
        return False

    logger.info("LangSmith tracing enabled: project=%s", project_name)
    _configured = True
    return True


def tracing_active() -> bool:
    return os.getenv("LANGCHAIN_TRACING_V2") == "true"


def reset_for_testing():
    """
    Test-only: clear cached state so configure_tracing() re-evaluates.

    Also clears the three module globals _install_default_tracing_client()
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
