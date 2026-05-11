import json
import socket
import urllib.request

import pytest

from cost_tracker.api_server import start_server
from cost_tracker.config import Settings
from cost_tracker.db import get_conn, init_db, set_rate, upsert_author, upsert_overhead, upsert_worklog
from cost_tracker.jira_client import WorklogEntry


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]  # type: ignore[return-value]


@pytest.fixture
def api_settings(env_defaults: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    port = _free_port()
    monkeypatch.setenv("API_PORT", str(port))
    return Settings()


@pytest.fixture(autouse=True)
def seeded_db(api_settings: Settings) -> None:
    init_db(api_settings.db_path)
    with get_conn(api_settings.db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        upsert_worklog(
            conn,
            WorklogEntry(
                worklog_id="wl1",
                issue_key="CSP-1",
                project_key="CSP",
                issue_summary="Test issue",
                author_account_id="acc1",
                author_display_name="Alice",
                time_spent_seconds=3600,
                started="2026-05-11T09:00:00.000+0000",
                assignee_account_id="acc1",
                assignee_display_name="Alice",
            ),
            "2026-05-11T10:00:00",
        )


@pytest.fixture
def server(api_settings: Settings):  # type: ignore[no-untyped-def]
    srv = start_server(api_settings)
    yield srv
    srv.shutdown()


def _get(port: int, path: str) -> list[dict]:  # type: ignore[type-arg]
    with urllib.request.urlopen(f"http://localhost:{port}{path}") as resp:
        return json.loads(resp.read())  # type: ignore[no-any-return]


def test_assignees_returns_data(server: object, api_settings: Settings) -> None:
    data = _get(api_settings.api_port, "/assignees")
    assert len(data) == 1
    assert data[0]["display_name"] == "Alice"
    assert data[0]["man_days"] == 0.5
    assert data[0]["cost_eur"] == 400.0


def test_issues_returns_data(server: object, api_settings: Settings) -> None:
    data = _get(api_settings.api_port, "/issues")
    assert len(data) == 1
    assert data[0]["issue_key"] == "CSP-1"
    assert data[0]["hours"] == 1.0


def test_worklogs_returns_data(server: object, api_settings: Settings) -> None:
    data = _get(api_settings.api_port, "/worklogs")
    assert len(data) == 1
    assert data[0]["worklog_id"] == "wl1"
    assert data[0]["assignee_display_name"] == "Alice"


def test_overhead_returns_data(server: object, api_settings: Settings) -> None:
    with get_conn(api_settings.db_path) as conn:
        upsert_overhead(conn, "acc1", "2026-05-11", "Overhead", 2.0)
    data = _get(api_settings.api_port, "/overhead")
    assert len(data) == 1
    assert data[0]["display_name"] == "Alice"
    assert data[0]["category"] == "Overhead"
    assert data[0]["total_hours"] == 2.0


def test_unknown_path_returns_404(server: object, api_settings: Settings) -> None:
    try:
        urllib.request.urlopen(f"http://localhost:{api_settings.api_port}/nope")
        assert False, "expected 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404
