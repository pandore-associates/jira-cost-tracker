import sqlite3
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label

from cost_tracker.config import Settings
from cost_tracker.db import get_conn, get_rates, set_rate


class RateInputScreen(ModalScreen[float | None]):
    """Modal dialog: enter hourly rate for one person."""

    DEFAULT_CSS = """
    RateInputScreen {
        align: center middle;
    }
    RateInputScreen > Label {
        margin-bottom: 1;
    }
    """

    def __init__(self, person: str, current: float | None) -> None:
        super().__init__()
        self._person = person
        self._current = current

    def compose(self) -> ComposeResult:
        current_str = f"{self._current:.2f}" if self._current is not None else ""
        yield Label(f"Hourly rate for {self._person} (€/h):")
        yield Input(value=current_str, placeholder="e.g. 150.00", id="rate-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.dismiss(float(event.value))
        except ValueError:
            self.dismiss(None)

    def on_key(self, event: object) -> None:
        from textual.events import Key
        if isinstance(event, Key) and event.key == "escape":
            self.dismiss(None)


class RatesTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._rows: list[sqlite3.Row] = []

    def compose(self) -> ComposeResult:
        yield DataTable(id="rates-table", cursor_type="row")

    def on_mount(self) -> None:
        t = self.query_one("#rates-table", DataTable)
        t.add_columns("Person", "Rate (€/h)", "Updated")
        self.refresh_data()

    def refresh_data(self) -> None:
        t = self.query_one("#rates-table", DataTable)
        t.clear()
        with get_conn(self._settings.db_path) as conn:
            self._rows = get_rates(conn)
        for row in self._rows:
            rate = f"€ {row['rate_eur']:.2f}" if row["rate_eur"] is not None else "— not set"
            updated = row["updated_at"][:10] if row["updated_at"] else "—"
            t.add_row(row["display_name"], rate, updated)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if idx >= len(self._rows):
            return
        row = self._rows[idx]

        def apply_rate(value: float | None) -> None:
            if value is not None:
                updated_at = datetime.now(timezone.utc).isoformat()
                with get_conn(self._settings.db_path) as conn:
                    set_rate(conn, str(row["account_id"]), value, updated_at)
                self.refresh_data()

        self.app.push_screen(RateInputScreen(str(row["display_name"]), row["rate_eur"]), apply_rate)
