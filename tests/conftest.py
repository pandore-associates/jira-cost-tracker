import pytest


@pytest.fixture
def env_defaults(monkeypatch, tmp_path):
    """Set minimal valid env vars and cd to tmp_path (no .env file there)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
    monkeypatch.setenv("JIRA_PROJECTS", "CSP")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
