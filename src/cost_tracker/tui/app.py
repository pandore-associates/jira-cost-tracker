from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from cost_tracker.config import Settings
from cost_tracker.sync import run_sync
from cost_tracker.tui.widgets.assignees_tab import AssigneesTab
from cost_tracker.tui.widgets.issues_tab import IssuesTab
from cost_tracker.tui.widgets.logs_tab import LogsTab
from cost_tracker.tui.widgets.overhead_tab import OverheadTab
from cost_tracker.tui.widgets.overview_tab import OverviewTab
from cost_tracker.tui.widgets.rates_tab import RatesTab


class CostTrackerApp(App[None]):
    TITLE = "Jira Cost Tracker"
    CSS = """
    .total-row { color: $success; text-style: bold; margin-top: 1; }
    IssuesTab, AssigneesTab, RatesTab, LogsTab, OverheadTab, OverviewTab { height: 1fr; }
    DataTable { height: 1fr; }
    #overhead-date { height: 1; }
    #overhead-summary { height: auto; }
    OverviewTab > Horizontal { height: 1fr; }
    #budget-chart, #mandays-chart { width: 1fr; height: 1fr; overflow: hidden hidden; }
    """
    BINDINGS = [
        ("s", "sync_now", "Sync Now"),
        ("e", "export_excel", "Export Excel"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Overview", id="overview"):
                yield OverviewTab(self._settings)
            with TabPane("By Issue", id="issues"):
                yield IssuesTab(self._settings)
            with TabPane("Overhead", id="overhead"):
                yield OverheadTab(self._settings)
            with TabPane("By Assignee", id="assignees"):
                yield AssigneesTab(self._settings)
            with TabPane("Rates", id="rates"):
                yield RatesTab(self._settings)
            with TabPane("Sync Log", id="logs"):
                yield LogsTab(self._settings)
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(5, self._refresh_all)

    def _refresh_all(self) -> None:
        for tab in [
            *self.query(OverviewTab),
            *self.query(IssuesTab),
            *self.query(AssigneesTab),
            *self.query(OverheadTab),
            *self.query(RatesTab),
            *self.query(LogsTab),
        ]:
            tab.refresh_data()

    def action_sync_now(self) -> None:
        self.run_worker(self._do_sync, exclusive=True, thread=True)

    def _do_sync(self) -> None:
        run_sync(self._settings)
        self.call_from_thread(self._refresh_all)

    def action_export_excel(self) -> None:
        from cost_tracker.exporter import export_excel
        path = export_excel(self._settings)
        self.notify(f"Exported to {path}", title="Export complete")
