import pytest

from cost_tracker.db import (
    finish_sync_run,
    get_assignees_with_cost,
    get_issues_with_cost,
    get_overhead_breakdown,
    get_overhead_for_date,
    get_rates,
    get_sync_runs,
    get_conn,
    init_db,
    set_rate,
    start_sync_run,
    upsert_author,
    upsert_overhead,
    upsert_worklog,
)
from cost_tracker.jira_client import WorklogEntry


@pytest.fixture
def db_path(tmp_path: pytest.TempPathFactory) -> str:
    path = str(tmp_path / "test.db")  # type: ignore[attr-defined]
    init_db(path)
    return path


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
        "assignee_account_id": "acc1",
        "assignee_display_name": "Alice",
    }
    defaults.update(kwargs)
    return WorklogEntry(**defaults)  # type: ignore[arg-type]


def test_upsert_worklog_stores_entry(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_worklog(conn, _wl(), "2026-05-11T10:00:00")
        row = conn.execute("SELECT * FROM worklogs WHERE worklog_id='wl1'").fetchone()
    assert row["issue_key"] == "CSP-1"
    assert row["time_spent_seconds"] == 3600


def test_upsert_worklog_replaces_on_conflict(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_worklog(conn, _wl(), "2026-05-11T10:00:00")
    with get_conn(db_path) as conn:
        upsert_worklog(conn, _wl(time_spent_seconds=7200), "2026-05-11T11:00:00")
        row = conn.execute("SELECT time_spent_seconds FROM worklogs WHERE worklog_id='wl1'").fetchone()
    assert row["time_spent_seconds"] == 7200


def test_upsert_author_inserts_with_null_rate(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        row = conn.execute("SELECT * FROM hourly_rates WHERE account_id='acc1'").fetchone()
    assert row["display_name"] == "Alice"
    assert row["rate_eur"] is None


def test_upsert_author_preserves_rate_on_re_upsert(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 150.0, "2026-05-11T10:00:00")
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice Renamed", "2026-05-11T11:00:00")
        row = conn.execute("SELECT * FROM hourly_rates WHERE account_id='acc1'").fetchone()
    assert row["display_name"] == "Alice Renamed"
    assert row["rate_eur"] == 150.0  # rate preserved


def test_sync_run_ok_lifecycle(db_path: str) -> None:
    with get_conn(db_path) as conn:
        sync_id = start_sync_run(conn, "2026-05-11T09:00:00")
    with get_conn(db_path) as conn:
        finish_sync_run(conn, sync_id, "2026-05-11T09:01:00", 5, None)
        row = conn.execute("SELECT * FROM sync_runs WHERE id=?", (sync_id,)).fetchone()
    assert row["status"] == "ok"
    assert row["worklogs_synced"] == 5
    assert row["error"] is None


def test_sync_run_error_lifecycle(db_path: str) -> None:
    with get_conn(db_path) as conn:
        sync_id = start_sync_run(conn, "2026-05-11T09:00:00")
    with get_conn(db_path) as conn:
        finish_sync_run(conn, sync_id, "2026-05-11T09:01:00", 0, "401 Unauthorized")
        row = conn.execute("SELECT * FROM sync_runs WHERE id=?", (sync_id,)).fetchone()
    assert row["status"] == "error"
    assert row["error"] == "401 Unauthorized"


def test_get_issues_with_cost(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        upsert_worklog(conn, _wl(time_spent_seconds=3600), "2026-05-11T10:00:00")
        rows = get_issues_with_cost(conn)
    assert len(rows) == 1
    assert rows[0]["issue_key"] == "CSP-1"
    assert rows[0]["hours"] == 1.0
    assert rows[0]["cost_eur"] == 100.0


def test_get_issues_with_missing_rate_shows_zero_cost(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        # no set_rate call
        upsert_worklog(conn, _wl(time_spent_seconds=3600), "2026-05-11T10:00:00")
        rows = get_issues_with_cost(conn)
    assert rows[0]["cost_eur"] == 0.0
    assert rows[0]["has_missing_rate"] == 1


def test_get_assignees_with_cost(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        upsert_worklog(
            conn,
            _wl(time_spent_seconds=7200, assignee_account_id="acc1", assignee_display_name="Alice"),
            "2026-05-11T10:00:00",
        )
        rows = get_assignees_with_cost(conn)
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Alice"
    assert rows[0]["man_days"] == 0.5  # 2 h ceiled to 1 half-day
    assert rows[0]["cost_eur"] == 400.0  # 0.5 day × €100/h × 8 h


def test_get_assignees_full_day_is_one_day(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        upsert_worklog(
            conn,
            _wl(time_spent_seconds=28800, assignee_account_id="acc1", assignee_display_name="Alice"),
            "2026-05-11T10:00:00",
        )
        rows = get_assignees_with_cost(conn)
    assert rows[0]["man_days"] == 1.0  # exactly 8 h = 1 day
    assert rows[0]["cost_eur"] == 800.0


def test_get_assignees_nine_hours_rounds_to_one_and_half_days(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        upsert_worklog(
            conn,
            _wl(time_spent_seconds=32400, assignee_account_id="acc1", assignee_display_name="Alice"),  # 9 h
            "2026-05-11T10:00:00",
        )
        rows = get_assignees_with_cost(conn)
    assert rows[0]["man_days"] == 1.5  # 9 h → ceil(9/4) = 3 half-days = 1.5 days
    assert rows[0]["cost_eur"] == 1200.0  # 1.5 × €100/h × 8 h


def test_get_assignees_groups_by_assignee_not_author(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "bob", "Bob", "2026-05-11T10:00:00")
        set_rate(conn, "bob", 50.0, "2026-05-11T10:00:00")
        # Alice logged time on an issue assigned to Bob
        upsert_worklog(
            conn,
            _wl(
                author_account_id="acc1",
                author_display_name="Alice",
                assignee_account_id="bob",
                assignee_display_name="Bob",
                time_spent_seconds=3600,
            ),
            "2026-05-11T10:00:00",
        )
        rows = get_assignees_with_cost(conn)
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Bob"
    assert rows[0]["man_days"] == 0.5  # 1 h ceiled to 1 half-day
    assert rows[0]["cost_eur"] == 200.0  # 0.5 day × €50/h × 8 h


def test_set_rate_updates_value(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 150.0, "2026-05-11T10:00:00")
        row = conn.execute("SELECT rate_eur FROM hourly_rates WHERE account_id='acc1'").fetchone()
    assert row["rate_eur"] == 150.0


def test_overhead_stacks_with_jira_for_man_days(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        set_rate(conn, "acc1", 100.0, "2026-05-11T10:00:00")
        # 3 h Jira + 2 h overhead = 5 h → ceil(5/4) = 2 half-days = 1.0 day
        upsert_worklog(
            conn,
            _wl(time_spent_seconds=10800, assignee_account_id="acc1", assignee_display_name="Alice"),
            "2026-05-11T10:00:00",
        )
        upsert_overhead(conn, "acc1", "2026-05-11", "Communication / Sync", 2.0)
        rows = get_assignees_with_cost(conn)
    assert rows[0]["jira_hours"] == 3.0
    assert rows[0]["overhead_hours"] == 2.0
    assert rows[0]["man_days"] == 1.0   # 5 h → 1 full day
    assert rows[0]["cost_eur"] == 800.0


def test_get_overhead_for_date(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        upsert_overhead(conn, "acc1", "2026-05-11", "Communication / Sync", 1.5)
        upsert_overhead(conn, "acc1", "2026-05-11", "Backlog Grooming", 0.5)
        upsert_overhead(conn, "acc1", "2026-05-12", "Communication / Sync", 2.0)
        rows = get_overhead_for_date(conn, "2026-05-11")
    assert len(rows) == 2
    cats = {row["category"]: row["hours"] for row in rows}
    assert cats["Communication / Sync"] == 1.5
    assert cats["Backlog Grooming"] == 0.5


def test_upsert_overhead_replaces_on_conflict(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        upsert_overhead(conn, "acc1", "2026-05-11", "Communication / Sync", 1.0)
        upsert_overhead(conn, "acc1", "2026-05-11", "Communication / Sync", 2.5)
        rows = get_overhead_for_date(conn, "2026-05-11")
    assert len(rows) == 1
    assert rows[0]["hours"] == 2.5


def test_get_overhead_breakdown(db_path: str) -> None:
    with get_conn(db_path) as conn:
        upsert_author(conn, "acc1", "Alice", "2026-05-11T10:00:00")
        upsert_overhead(conn, "acc1", "2026-05-11", "Communication / Sync", 1.0)
        upsert_overhead(conn, "acc1", "2026-05-12", "Communication / Sync", 2.0)
        upsert_overhead(conn, "acc1", "2026-05-11", "Backlog Grooming", 0.5)
        rows = get_overhead_breakdown(conn)
    totals = {row["category"]: row["total_hours"] for row in rows}
    assert totals["Communication / Sync"] == 3.0
    assert totals["Backlog Grooming"] == 0.5


def test_get_sync_runs_returns_most_recent_first(db_path: str) -> None:
    with get_conn(db_path) as conn:
        id1 = start_sync_run(conn, "2026-05-11T09:00:00")
    with get_conn(db_path) as conn:
        id2 = start_sync_run(conn, "2026-05-11T10:00:00")
    with get_conn(db_path) as conn:
        rows = get_sync_runs(conn)
    assert rows[0]["id"] == id2
    assert rows[1]["id"] == id1
