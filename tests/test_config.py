import pytest
from cost_tracker.config import Settings


def test_loads_required_fields(env_defaults):
    s = Settings()
    assert s.jira_base_url == "https://example.atlassian.net"
    assert s.jira_email == "test@example.com"
    assert s.jira_api_token == "test-token"


def test_parses_comma_separated_projects(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECTS", " CSP , XYZ ")
    s = Settings()
    assert s.jira_projects == ["CSP", "XYZ"]


def test_default_paths(env_defaults, tmp_path):
    s = Settings()
    assert s.db_path == str(tmp_path / "test.db")
    assert s.export_dir == str(tmp_path / "exports")
