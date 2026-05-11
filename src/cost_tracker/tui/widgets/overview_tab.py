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
) -> tuple[list[str], list[float], list[float]]:
    """Merge daily rows, fill date gaps, return (dates, cum_tasks, cum_tasks_plus_overhead)."""
    jira_by_date: dict[str, float] = {str(r["day"]): float(r[key]) for r in daily_jira}
    oh_by_date: dict[str, float] = {str(r["day"]): float(r[key]) for r in daily_overhead}

    all_dates = sorted(set(jira_by_date) | set(oh_by_date))
    if not all_dates:
        return [], [], []

    start = date.fromisoformat(all_dates[0])
    end = date.today()

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
        plt.plot(x_span, [band_min, band_min], label=f"Plan  ({band_min:,.0f})", color="green")
        plt.plot(x_span, [band_max, band_max], label=f"+30%  ({band_max:,.0f})", color="red")

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

        # --- Budget chart (€) ---
        dates, cum_cost_tasks, cum_cost_total = _merge_cumulative(jira_rows, overhead_rows, "cost")
        budget_min = self._settings.plan_budget_eur
        budget_max = round(budget_min * (1 + self._settings.plan_contingency), 2)
        budget_chart = _render_chart(
            "Budget  (€)",
            dates, cum_cost_tasks, cum_cost_total,
            budget_min, budget_max,
            "€",
            chart_w, chart_h,
        )

        # --- Man-days chart ---
        dates2, cum_h_tasks, cum_h_total = _merge_cumulative(jira_rows, overhead_rows, "hours")
        cum_days_tasks = [round(h / 8, 2) for h in cum_h_tasks]
        cum_days_total = [round(h / 8, 2) for h in cum_h_total]
        days_min = self._settings.plan_man_days
        days_max = round(days_min * (1 + self._settings.plan_contingency), 1)
        mandays_chart = _render_chart(
            "Man-days",
            dates2, cum_days_tasks, cum_days_total,
            days_min, days_max,
            "days",
            chart_w, chart_h,
        )

        self.query_one("#budget-chart", Static).update(budget_chart)
        self.query_one("#mandays-chart", Static).update(mandays_chart)
