import sqlite3

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from cost_tracker.config import Settings
from cost_tracker.db import get_conn, get_issues_with_cost


class IssuesTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        yield DataTable(id="issues-table")
        yield Static("", id="issues-total", classes="total-row")

    def on_mount(self) -> None:
        t = self.query_one("#issues-table", DataTable)
        t.add_columns("Key", "Summary", "Project", "Hours", "Cost (€)")
        self.refresh_data()

    def refresh_data(self) -> None:
        t = self.query_one("#issues-table", DataTable)
        t.clear()
        total = 0.0
        with get_conn(self._settings.db_path) as conn:
            rows: list[sqlite3.Row] = get_issues_with_cost(conn)
        for row in rows:
            cost: float = row["cost_eur"] or 0.0
            total += cost
            t.add_row(
                row["issue_key"],
                row["issue_summary"],
                row["project_key"],
                f"{row['hours']:.1f} h",
                f"€ {cost:,.2f}",
            )
        self.query_one("#issues-total", Static).update(f"Total: € {total:,.2f}")
