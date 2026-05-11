from datetime import date, timedelta
from typing import Any

import plotext as plt  # type: ignore[import]
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from cost_tracker.config import Settings
from cost_tracker.db import get_conn, get_daily_jira_data, get_daily_overhead_data


def _merge_cumulative(
    daily_jira: list[Any],
    daily_overhead: list[Any],
    key: str,
    start: date,
    end: date,
) -> tuple[list[str], list[float], list[float]]:
    """Merge daily rows over [start, end], return (dates, cum_tasks, cum_tasks_plus_overhead)."""
    jira_by_date: dict[str, float] = {str(r["day"]): float(r[key]) for r in daily_jira}
    oh_by_date: dict[str, float] = {str(r["day"]): float(r[key]) for r in daily_overhead}

    dates: list[str] = []
    cum_tasks: list[float] = []
    cum_total: list[float] = []
    t_sum = 0.0
    o_sum = 0.0

    d = start
    while d <= end:
        ds = d.isoformat()
        t_sum += jira_by_date.get(ds, 0.0)
        o_sum += oh_by_date.get(ds, 0.0)
        dates.append(ds)
        cum_tasks.append(round(t_sum, 2))
        cum_total.append(round(t_sum + o_sum, 2))
        d += timedelta(days=1)

    return dates, cum_tasks, cum_total


def _render_chart(
    title: str,
    dates: list[str],
    line_tasks: list[float],
    line_total: list[float],
    band_min: float,
    band_max: float,
    y_label: str,
    width: int,
    height: int,
) -> Text:
    plt.clear_figure()
    plt.plotsize(width, height)
    plt.title(title)
    plt.theme("dark")
    plt.ylabel(y_label)

    if not dates:
        plt.text("No data yet", 0.5, 0.5)
    else:
        xs = list(range(len(dates)))

        # X-axis: show ~6 evenly spaced date labels
        step = max(1, len(dates) // 6)
        ticks = xs[::step]
        plt.xticks(ticks, [dates[i] for i in ticks])

        plt.plot(xs, line_tasks, label="Tasks (Jira)", color="cyan")
        plt.plot(xs, line_total, label="Tasks + Overhead", color="orange")

        # Budget / plan band
        x_span = [0, len(dates) - 1] if len(dates) > 1 else [0, 0]
        plt.plot(x_span, [band_min, band_min], label=f"Plan  ({band_min:.0f}%)", color="green")
        plt.plot(x_span, [band_max, band_max], label=f"+{band_max - band_min:.0f}%  ({band_max:.0f}%)", color="red")

    return Text.from_ansi(plt.build())


class OverviewTab(Widget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", id="budget-chart")
            yield Static("", id="mandays-chart")

    def on_mount(self) -> None:
        self.refresh_data()

    def on_resize(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        w = self.size.width
        h = self.size.height
        if w < 10 or h < 5:
            return

        with get_conn(self._settings.db_path) as conn:
            jira_rows = get_daily_jira_data(conn)
            overhead_rows = get_daily_overhead_data(conn)

        chart_w = max(10, w // 2 - 2)
        chart_h = max(5, h - 2)
        contingency_pct = self._settings.plan_contingency * 100
        plan_start = date.fromisoformat(self._settings.plan_start)
        plan_end = date.fromisoformat(self._settings.plan_end)

        # --- Budget chart (% of plan) ---
        dates, cum_cost_tasks, cum_cost_total = _merge_cumulative(
            jira_rows, overhead_rows, "cost", plan_start, plan_end
        )
        budget_base = self._settings.plan_budget_eur or 1.0
        pct_cost_tasks = [round(v / budget_base * 100, 2) for v in cum_cost_tasks]
        pct_cost_total = [round(v / budget_base * 100, 2) for v in cum_cost_total]
        budget_chart = _render_chart(
            f"Budget  (% of {budget_base:,.0f} €)",
            dates, pct_cost_tasks, pct_cost_total,
            100.0, round(100 + contingency_pct, 1),
            "%",
            chart_w, chart_h,
        )

        # --- Man-days chart (% of plan) ---
        dates2, cum_h_tasks, cum_h_total = _merge_cumulative(
            jira_rows, overhead_rows, "hours", plan_start, plan_end
        )
        days_base = self._settings.plan_man_days or 1.0
        pct_days_tasks = [round(h / 8 / days_base * 100, 2) for h in cum_h_tasks]
        pct_days_total = [round(h / 8 / days_base * 100, 2) for h in cum_h_total]
        mandays_chart = _render_chart(
            f"Man-days  (% of {days_base:.0f} d)",
            dates2, pct_days_tasks, pct_days_total,
            100.0, round(100 + contingency_pct, 1),
            "%",
            chart_w, chart_h,
        )

        self.query_one("#budget-chart", Static).update(budget_chart)
        self.query_one("#mandays-chart", Static).update(mandays_chart)
