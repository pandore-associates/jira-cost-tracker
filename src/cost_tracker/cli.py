from __future__ import annotations

from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from cost_tracker.config import Settings

app = typer.Typer(help="Jira worklog cost tracker", no_args_is_help=True)


def _settings() -> Settings:
    from cost_tracker.config import Settings
    try:
        return Settings()
    except Exception as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def daemon() -> None:
    """Run the scheduled sync daemon (09:00-12:00, 14:00-18:00 hourly)."""
    from cost_tracker.scheduler import run_daemon
    s = _settings()
    if not s.jira_api_token:
        typer.echo("JIRA_API_TOKEN is not set.", err=True)
        raise typer.Exit(1)
    run_daemon(s)


@app.command()
def sync() -> None:
    """Run a one-off sync immediately."""
    from cost_tracker.db import init_db
    from cost_tracker.sync import run_sync
    s = _settings()
    init_db(s.db_path)
    typer.echo("Syncing…")
    count, error = run_sync(s)
    if error:
        typer.echo(f"Sync failed: {error}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Done. {count} worklogs synced.")


@app.command()
def tui() -> None:
    """Open the interactive TUI."""
    from cost_tracker.db import init_db
    from cost_tracker.tui.app import CostTrackerApp
    s = _settings()
    if not s.jira_api_token:
        typer.echo("JIRA_API_TOKEN is not set.", err=True)
        raise typer.Exit(1)
    init_db(s.db_path)
    CostTrackerApp(s).run()


@app.command()
def export() -> None:
    """Export current data to Excel."""
    from cost_tracker.exporter import export_excel
    s = _settings()
    path = export_excel(s)
    typer.echo(f"Exported to {path}")
