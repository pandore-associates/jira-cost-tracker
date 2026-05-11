import sqlite3
from contextlib import contextmanager
from typing import Generator

from cost_tracker.jira_client import WorklogEntry

_SCHEMA = """\
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS hourly_rates (
    account_id   TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    rate_eur     REAL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worklogs (
    worklog_id            TEXT PRIMARY KEY,
    issue_key             TEXT NOT NULL,
    project_key           TEXT NOT NULL,
    issue_summary         TEXT NOT NULL,
    author_account_id     TEXT NOT NULL,
    author_display_name   TEXT NOT NULL,
    time_spent_seconds    INTEGER NOT NULL,
    started               TEXT NOT NULL,
    synced_at             TEXT NOT NULL,
    assignee_account_id   TEXT,
    assignee_display_name TEXT
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    status           TEXT NOT NULL DEFAULT 'running',
    worklogs_synced  INTEGER NOT NULL DEFAULT 0,
    error            TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    project_key  TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1
);
"""


@contextmanager
def get_conn(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_MIGRATIONS = [
    "ALTER TABLE worklogs ADD COLUMN assignee_account_id TEXT",
    "ALTER TABLE worklogs ADD COLUMN assignee_display_name TEXT",
]


def init_db(db_path: str) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(_SCHEMA)
    with get_conn(db_path) as conn:
        for sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


def upsert_worklog(conn: sqlite3.Connection, wl: WorklogEntry, synced_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO worklogs
           (worklog_id, issue_key, project_key, issue_summary,
            author_account_id, author_display_name, time_spent_seconds, started, synced_at,
            assignee_account_id, assignee_display_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            wl.worklog_id, wl.issue_key, wl.project_key, wl.issue_summary,
            wl.author_account_id, wl.author_display_name, wl.time_spent_seconds,
            wl.started, synced_at,
            wl.assignee_account_id, wl.assignee_display_name,
        ),
    )


def upsert_author(
    conn: sqlite3.Connection, account_id: str, display_name: str, updated_at: str
) -> None:
    conn.execute(
        """INSERT INTO hourly_rates (account_id, display_name, rate_eur, updated_at)
           VALUES (?, ?, NULL, ?)
           ON CONFLICT(account_id) DO UPDATE SET display_name=excluded.display_name""",
        (account_id, display_name, updated_at),
    )


def start_sync_run(conn: sqlite3.Connection, started_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO sync_runs (started_at, status, worklogs_synced) VALUES (?, 'running', 0)",
        (started_at,),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def finish_sync_run(
    conn: sqlite3.Connection,
    sync_id: int,
    finished_at: str,
    worklogs_synced: int,
    error: str | None,
) -> None:
    conn.execute(
        """UPDATE sync_runs
           SET finished_at=?, status=?, worklogs_synced=?, error=?
           WHERE id=?""",
        (finished_at, "error" if error else "ok", worklogs_synced, error, sync_id),
    )


def get_issues_with_cost(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(  # type: ignore[return-value]
        """SELECT
               w.issue_key,
               w.project_key,
               w.issue_summary,
               ROUND(SUM(w.time_spent_seconds) / 3600.0, 2) AS hours,
               ROUND(SUM(w.time_spent_seconds / 3600.0 * COALESCE(r.rate_eur, 0)), 2) AS cost_eur,
               MAX(CASE WHEN r.rate_eur IS NULL THEN 1 ELSE 0 END) AS has_missing_rate
           FROM worklogs w
           LEFT JOIN hourly_rates r ON w.assignee_account_id = r.account_id
           GROUP BY w.issue_key
           ORDER BY cost_eur DESC"""
    ).fetchall()


def get_assignees_with_cost(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    # Cost is ceiled to the nearest half man-day (4 h) per assignee before multiplying by rate.
    # half_days = integer ceiling of (total_seconds / 14400)  (14400 = 4 * 3600)
    # man_days  = half_days * 0.5
    # cost      = half_days * rate_eur * 4
    return conn.execute(  # type: ignore[return-value]
        """SELECT
               COALESCE(w.assignee_account_id, '') AS account_id,
               COALESCE(w.assignee_display_name, 'Unassigned') AS display_name,
               r.rate_eur,
               COUNT(DISTINCT w.issue_key) AS issue_count,
               (SUM(w.time_spent_seconds) + 14399) / 14400 * 0.5 AS man_days,
               ROUND((SUM(w.time_spent_seconds) + 14399) / 14400 * COALESCE(r.rate_eur, 0) * 4, 2) AS cost_eur
           FROM worklogs w
           LEFT JOIN hourly_rates r ON w.assignee_account_id = r.account_id
           GROUP BY COALESCE(w.assignee_account_id, '')
           ORDER BY cost_eur DESC"""
    ).fetchall()


def get_sync_runs(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(  # type: ignore[return-value]
        "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def get_rates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(  # type: ignore[return-value]
        "SELECT account_id, display_name, rate_eur, updated_at FROM hourly_rates ORDER BY display_name"
    ).fetchall()


def set_rate(
    conn: sqlite3.Connection, account_id: str, rate_eur: float, updated_at: str
) -> None:
    conn.execute(
        "UPDATE hourly_rates SET rate_eur=?, updated_at=? WHERE account_id=?",
        (rate_eur, updated_at, account_id),
    )


def upsert_project(conn: sqlite3.Connection, project_key: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_key, project_name, enabled) VALUES (?, ?, 1)",
        (project_key, project_key),
    )
