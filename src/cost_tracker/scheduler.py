from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import]
from loguru import logger

from cost_tracker.api_server import start_server
from cost_tracker.config import Settings
from cost_tracker.db import init_db
from cost_tracker.sync import run_sync


def run_daemon(settings: Settings) -> None:
    """Start the blocking APScheduler daemon with a JSON API server."""
    init_db(settings.db_path)
    start_server(settings)
    logger.info(
        f"API server listening on http://localhost:{settings.api_port} "
        f"— endpoints: /assignees  /issues  /worklogs"
    )
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_sync,
        CronTrigger(hour="9-12,14-18", minute=0),
        args=[settings],
        id="sync",
        name="Jira worklog sync",
    )
    logger.info(
        f"Daemon started. Schedule: 09:00-12:00 and 14:00-18:00 hourly. "
        f"Projects: {settings.jira_projects}. DB: {settings.db_path}"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Daemon stopped.")
