from datetime import date, timedelta
from typing import Any

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, Static

from cost_tracker.config import Settings
from cost_tracker.db import (
    OVERHEAD_CATEGORIES,
    get_assignees_with_cost,
    get_conn,
    get_overhead_breakdown,
    get_overhead_for_date,
    get_rates,
    upsert_overhead,
)


class HoursInputScreen(ModalScreen[float | None]):
    DEFAULT_CSS = """
    HoursInputScreen { align: center middle; }
    HoursInputScreen > Label { margin-bottom: 1; }
    """

    def __init__(self, person: str, category: str, current: float) -> None:
        super().__init__()
        self._person = person
        self._category = category
        self._current = current

    def compose(self) -> ComposeResult:
        current_str = f"{self._current:.1f}" if self._current else ""
        yield Label(f"{self._person}  —  {self._category} (h):")
        yield Input(value=current_str, placeholder="e.g. 1.5", id="hours-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.dismiss(float(event.value))
        except ValueError:
            self.dismiss(None)

    def on_key(self, event: object) -> None:
        from textual.events import Key
        if isinstance(event, Key) and event.key == "escape":
            self.dismiss(None)


class OverheadTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._date = date.today().isoformat()
        self._rows: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="overhead-date")
        yield DataTable(id="overhead-table", cursor_type="row")
        yield Static("", id="overhead-summary")

    def on_mount(self) -> None:
        t = self.query_one("#overhead-table", DataTable)
        t.add_columns("Person", "Category", "Hours")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.query_one("#overhead-date", Static).update(
            f"  {self._date}   [ ← prev   next → ]"
        )
        t = self.query_one("#overhead-table", DataTable)
        t.clear()
        self._rows = []

        with get_conn(self._settings.db_path) as conn:
            people = get_rates(conn)
            today_entries = {
                (row["account_id"], row["category"]): row["hours"]
                for row in get_overhead_for_date(conn, self._date)
            }
            assignee_rows = get_assignees_with_cost(conn)
            jira_hours_by_id = {
                row["account_id"]: float(row["jira_hours"] or 0.0)
                for row in assignee_rows
            }
            breakdown = get_overhead_breakdown(conn)

        for person in people:
            for cat in OVERHEAD_CATEGORIES:
                hours = today_entries.get((person["account_id"], cat), 0.0)
                self._rows.append({
                    "account_id": person["account_id"],
                    "display_name": person["display_name"],
                    "category": cat,
                    "hours": hours,
                })
                t.add_row(person["display_name"], cat, f"{hours:.1f} h")

        # Global Tasks / Overhead % across all profiles.
        # Tasks  = Jira hours (all assignees) + manual "Tasks" entries
        # Overhead = manual "Overhead" entries
        cat_totals: dict[str, float] = {}
        for row in breakdown:
            cat = str(row["category"])
            cat_totals[cat] = cat_totals.get(cat, 0.0) + float(row["total_hours"])

        total_jira = sum(jira_hours_by_id.values())
        total_tasks = total_jira + cat_totals.get("Tasks", 0.0)
        total_overhead = cat_totals.get("Overhead", 0.0)
        grand_total = total_tasks + total_overhead

        if grand_total > 0:
            tp = int(round(total_tasks / grand_total * 100))
            op = int(round(total_overhead / grand_total * 100))
            summary = f"All profiles — Tasks {tp}%   Overhead {op}%"
        else:
            summary = ""

        self.query_one("#overhead-summary", Static).update(summary)

    def on_key(self, event: object) -> None:
        from textual.events import Key
        if not isinstance(event, Key):
            return
        if event.character == "[":
            self._date = (date.fromisoformat(self._date) - timedelta(days=1)).isoformat()
            self.refresh_data()
        elif event.character == "]":
            self._date = (date.fromisoformat(self._date) + timedelta(days=1)).isoformat()
            self.refresh_data()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if idx >= len(self._rows):
            return
        row = self._rows[idx]

        def apply(value: float | None) -> None:
            if value is not None and value >= 0:
                with get_conn(self._settings.db_path) as conn:
                    upsert_overhead(
                        conn, row["account_id"], self._date, row["category"], value
                    )
                self.refresh_data()

        self.app.push_screen(
            HoursInputScreen(row["display_name"], row["category"], row["hours"]),
            apply,
        )
