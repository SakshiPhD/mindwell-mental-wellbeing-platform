"""
Regression tests for database.py::_load_db_credentials — the fix for DB
connections silently failing when the app was launched from source_code/
(as the setup docs instruct) instead of the project root, because
st.secrets resolves .streamlit/secrets.toml relative to the current working
directory. The direct-file-read path is tested elsewhere by hand against
the real local secrets.toml (see project notes); this suite covers the
portable parts that don't depend on any machine-specific file existing, so
it passes on a fresh checkout too.
"""
import os
import database


def test_env_var_fallback_used_when_no_secrets_file(monkeypatch, tmp_path):
    """With no real secrets.toml reachable and st.secrets unavailable, env
    vars (the .env-based configuration the setup docs describe) must work."""
    # Point the module at a directory with no .streamlit/secrets.toml in it.
    monkeypatch.setattr(database, "__file__", str(tmp_path / "source_code" / "database.py"))
    # Make the st.secrets fallback fail, matching a bare/no-secrets environment.
    monkeypatch.setattr(
        database.st, "secrets", {}, raising=False
    )
    monkeypatch.setenv("DB_HOST", "example-host.neon.tech")
    monkeypatch.setenv("DB_NAME", "neondb")
    monkeypatch.setenv("DB_USER", "testuser")
    monkeypatch.setenv("DB_PASSWORD", "testpass")
    monkeypatch.setenv("DB_PORT", "5432")

    creds = database._load_db_credentials()
    assert creds is not None
    assert creds["host"] == "example-host.neon.tech"
    assert creds["database"] == "neondb"
    assert creds["user"] == "testuser"
    assert creds["password"] == "testpass"


def test_returns_none_when_nothing_available(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "__file__", str(tmp_path / "source_code" / "database.py"))
    monkeypatch.setattr(database.st, "secrets", {}, raising=False)
    for var in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_PORT"):
        monkeypatch.delenv(var, raising=False)

    assert database._load_db_credentials() is None


def test_direct_file_read_is_independent_of_cwd(monkeypatch, tmp_path):
    """The actual bug: launching from a different working directory must not
    change whether credentials are found, when a real secrets.toml exists
    at a fixed location relative to this module."""
    fake_project_root = tmp_path / "project"
    fake_source_dir = fake_project_root / "source_code"
    fake_streamlit_dir = fake_project_root / ".streamlit"
    fake_source_dir.mkdir(parents=True)
    fake_streamlit_dir.mkdir(parents=True)
    (fake_streamlit_dir / "secrets.toml").write_text(
        '[postgres]\n'
        'host = "fixture-host.neon.tech"\n'
        'database = "fixturedb"\n'
        'user = "fixtureuser"\n'
        'password = "fixturepass"\n'
        'port = 5432\n'
        'sslmode = "require"\n'
    )
    monkeypatch.setattr(database, "__file__", str(fake_source_dir / "database.py"))
    monkeypatch.setattr(database.st, "secrets", {}, raising=False)

    other_dir = tmp_path / "somewhere" / "else"
    other_dir.mkdir(parents=True)
    original_cwd = os.getcwd()
    try:
        os.chdir(str(other_dir))
        creds = database._load_db_credentials()
    finally:
        os.chdir(original_cwd)

    assert creds is not None
    assert creds["host"] == "fixture-host.neon.tech"
    assert creds["database"] == "fixturedb"
