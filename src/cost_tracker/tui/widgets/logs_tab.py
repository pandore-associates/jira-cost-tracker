import sqlite3

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable

from cost_tracker.config import Settings
from cost_tracker.db import get_conn, get_sync_runs


class LogsTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        yield DataTable(id="logs-table")

    def on_mount(self) -> None:
        t = self.query_one("#logs-table", DataTable)
        t.add_columns("Started", "Status", "Worklogs", "Error")
        self.refresh_data()

    def refresh_data(self) -> None:
        t = self.query_one("#logs-table", DataTable)
        t.clear()
        with get_conn(self._settings.db_path) as conn:
            rows: list[sqlite3.Row] = get_sync_runs(conn)
        for row in rows:
            started = str(row["started_at"])[:16] if row["started_at"] else "—"
            t.add_row(
                started,
                str(row["status"]),
                str(row["worklogs_synced"]),
                str(row["error"]) if row["error"] else "—",
            )
