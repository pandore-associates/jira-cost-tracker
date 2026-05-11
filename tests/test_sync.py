from unittest.mock import MagicMock, patch

import pytest

from cost_tracker.config import Settings
from cost_tracker.db import get_conn, init_db
from cost_tracker.jira_client import WorklogEntry
from cost_tracker.sync import run_sync


@pytest.fixture
def settings(env_defaults: None) -> Settings:
    return Settings()


@pytest.fixture(autouse=True)
def setup_db(settings: Settings) -> None:
    init_db(settings.db_path)


def _wl(**kwargs: object) -> WorklogEntry:
    defaults: dict[str, object] = {
        "worklog_id": "wl1",
        "issue_key": "CSP-1",
        "project_key": "CSP",
        "issue_summary": "Test issue",
        "author_account_id": "acc1",
        "author_display_name": "Alice",
        "time_spent_seconds": 3600,
        "started": "2026-05-11T09:00:00.000+0000",
    }
    defaults.update(kwargs)
    return WorklogEntry(**defaults)  # type: ignore[arg-type]


@patch("cost_tracker.sync.JiraClient")
def test_run_sync_stores_worklogs(MockClient: MagicMock, settings: Settings) -> None:
    MockClient.return_value.get_worklogs_for_project.return_value = [_wl()]

    count, error = run_sync(settings)

    assert count == 1
    assert error is None
    with get_conn(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM worklogs WHERE worklog_id='wl1'").fetchone()
    assert row is not None


@patch("cost_tracker.sync.JiraClient")
def test_run_sync_upserts_author(MockClient: MagicMock, settings: Settings) -> None:
    MockClient.return_value.get_worklogs_for_project.return_value = [_wl()]

    run_sync(settings)

    with get_conn(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM hourly_rates WHERE account_id='acc1'").fetchone()
    assert row["display_name"] == "Alice"


@patch("cost_tracker.sync.JiraClient")
def test_run_sync_records_ok_run(MockClient: MagicMock, settings: Settings) -> None:
    MockClient.return_value.get_worklogs_for_project.return_value = [_wl()]

    run_sync(settings)

    with get_conn(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM sync_runs").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["worklogs_synced"] == 1


@patch("cost_tracker.sync.JiraClient")
def test_run_sync_records_error_on_api_failure(MockClient: MagicMock, settings: Settings) -> None:
    MockClient.return_value.get_worklogs_for_project.side_effect = Exception("timeout")

    count, error = run_sync(settings)

    assert count == 0
    assert error == "timeout"
    with get_conn(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM sync_runs").fetchall()
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "timeout"
