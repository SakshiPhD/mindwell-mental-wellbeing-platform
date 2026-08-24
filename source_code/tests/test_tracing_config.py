"""
Tests for tracing.py's config resolution and fail-open behavior. These run
entirely without a real LangSmith account — same portability principle as
test_db_credentials.py: verify the logic, not a live service.

The one thing NOT re-tested here (verified by hand instead, see the
milestone notes): that a real, deliberately-invalid LangSmith API key lets
a real conversation complete normally. That needs an actual network call to
confirm LangSmith's own upload-failure handling, which isn't something to
depend on in a fast unit-test suite — it was verified directly against a
live Ollama call.
"""
import tracing


def setup_function():
    tracing.reset_for_testing()


def teardown_function():
    tracing.reset_for_testing()


def test_defaults_to_inactive_with_no_config(monkeypatch, tmp_path):
    monkeypatch.setattr(tracing, "__file__", str(tmp_path / "source_code" / "tracing.py"))
    for var in ("LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_PROJECT"):
        monkeypatch.delenv(var, raising=False)

    result = tracing.configure_tracing(environment="development")

    assert result is False
    assert tracing.tracing_active() is False


def test_activates_with_env_var_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(tracing, "__file__", str(tmp_path / "source_code" / "tracing.py"))
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test_key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "mindwell")

    result = tracing.configure_tracing(environment="development")

    assert result is True
    assert tracing.tracing_active() is True
    import os
    assert os.environ["LANGCHAIN_PROJECT"] == "mindwell-development"
    assert os.environ["LANGCHAIN_API_KEY"] == "ls__test_key"


def test_project_name_not_double_suffixed(monkeypatch, tmp_path):
    """If the configured project name already ends with -development, don't
    append it again."""
    monkeypatch.setattr(tracing, "__file__", str(tmp_path / "source_code" / "tracing.py"))
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test_key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "mindwell-development")

    tracing.configure_tracing(environment="development")

    import os
    assert os.environ["LANGCHAIN_PROJECT"] == "mindwell-development"


def test_staging_and_development_get_different_project_names(monkeypatch, tmp_path):
    monkeypatch.setattr(tracing, "__file__", str(tmp_path / "source_code" / "tracing.py"))
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test_key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "mindwell")

    tracing.reset_for_testing()
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test_key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "mindwell")
    tracing.configure_tracing(environment="staging")
    import os
    assert os.environ["LANGCHAIN_PROJECT"] == "mindwell-staging"


def test_reads_from_secrets_toml_anchored_to_module_location(monkeypatch, tmp_path):
    """Same CWD-independence principle as the database credentials fix."""
    fake_source_dir = tmp_path / "project" / "source_code"
    fake_streamlit_dir = tmp_path / "project" / ".streamlit"
    fake_source_dir.mkdir(parents=True)
    fake_streamlit_dir.mkdir(parents=True)
    (fake_streamlit_dir / "secrets.toml").write_text(
        '[langsmith]\n'
        'api_key = "ls__from_secrets_file"\n'
        'project = "mindwell"\n'
    )
    monkeypatch.setattr(tracing, "__file__", str(fake_source_dir / "tracing.py"))
    for var in ("LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_PROJECT"):
        monkeypatch.delenv(var, raising=False)

    result = tracing.configure_tracing(environment="development")

    assert result is True
    import os
    assert os.environ["LANGCHAIN_API_KEY"] == "ls__from_secrets_file"
    assert os.environ["LANGCHAIN_PROJECT"] == "mindwell-development"


def test_configure_tracing_is_idempotent(monkeypatch, tmp_path):
    """Calling it twice shouldn't re-read config or error."""
    monkeypatch.setattr(tracing, "__file__", str(tmp_path / "source_code" / "tracing.py"))
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test_key")

    first = tracing.configure_tracing(environment="development")
    second = tracing.configure_tracing(environment="development")

    assert first == second is True
