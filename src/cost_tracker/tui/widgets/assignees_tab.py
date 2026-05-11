import sqlite3

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from cost_tracker.config import Settings
from cost_tracker.db import get_assignees_with_cost, get_conn


class AssigneesTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        yield DataTable(id="assignees-table")
        yield Static("", id="assignees-total", classes="total-row")

    def on_mount(self) -> None:
        t = self.query_one("#assignees-table", DataTable)
        t.add_columns("Assignee", "Issues", "Days", "Cost (€)", "Rate (€/h)")
        self.refresh_data()

    def refresh_data(self) -> None:
        t = self.query_one("#assignees-table", DataTable)
        t.clear()
        total = 0.0
        with get_conn(self._settings.db_path) as conn:
            rows: list[sqlite3.Row] = get_assignees_with_cost(conn)
        for row in rows:
            cost: float = row["cost_eur"] or 0.0
            total += cost
            rate = f"€ {row['rate_eur']:.2f}" if row["rate_eur"] is not None else "— not set"
            t.add_row(
                row["display_name"],
                str(row["issue_count"]),
                f"{row['man_days']:.1f}",
                f"€ {cost:,.2f}",
                rate,
            )
        self.query_one("#assignees-total", Static).update(f"Total: € {total:,.2f}")
