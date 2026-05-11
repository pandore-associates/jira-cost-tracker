from datetime import datetime, timezone

from loguru import logger

from cost_tracker.config import Settings
from cost_tracker.db import (
    finish_sync_run,
    get_conn,
    start_sync_run,
    upsert_author,
    upsert_project,
    upsert_worklog,
)
from cost_tracker.jira_client import JiraClient


def run_sync(settings: Settings) -> tuple[int, str | None]:
    """Fetch worklogs for all configured projects and store them.

    Returns (worklogs_synced, error_message | None).
    """
    client = JiraClient(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    started_at = datetime.now(timezone.utc).isoformat()

    with get_conn(settings.db_path) as conn:
        sync_id = start_sync_run(conn, started_at)
        for key in settings.jira_projects:
            upsert_project(conn, key)

    total = 0
    error_msg: str | None = None
    try:
        for project_key in settings.jira_projects:
            logger.info(f"Syncing project {project_key}")
            worklogs = client.get_worklogs_for_project(project_key)
            synced_at = datetime.now(timezone.utc).isoformat()
            with get_conn(settings.db_path) as conn:
                for wl in worklogs:
                    upsert_worklog(conn, wl, synced_at)
                    upsert_author(conn, wl.author_account_id, wl.author_display_name, synced_at)
            total += len(worklogs)
            logger.info(f"Synced {len(worklogs)} worklogs for {project_key}")
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Sync error: {exc}")

    finished_at = datetime.now(timezone.utc).isoformat()
    with get_conn(settings.db_path) as conn:
        finish_sync_run(conn, sync_id, finished_at, total, error_msg)

    return total, error_msg
