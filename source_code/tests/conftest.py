"""
Shared pytest setup. Adds source_code/ to sys.path so tests can import the
app modules (database, engine, pages, llm_provider) directly, regardless of
which directory pytest is invoked from.

These tests deliberately avoid real Ollama or database calls — they target
the deterministic, pure-Python logic (keyword/regex matching, filtering,
extraction) that every bug fixed in the "baseline stabilization" pass lived
in. That keeps the suite fast and non-flaky, and matches the project's own
distinction between software testing (does the implementation work?) and
LLM evaluation (does the probabilistic behavior meet expectations?) — this
suite is the former.
"""
import os
import sys

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

# streamlit's own modules print a "missing ScriptRunContext" warning when
# imported outside a real `streamlit run` session. Harmless for these tests
# (none of them touch st.session_state) but noisy — silence it.
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")
