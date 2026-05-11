import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from cost_tracker.config import Settings
from cost_tracker.db import get_assignees_with_cost, get_conn, get_issues_with_cost, get_overhead_breakdown


def _make_handler(settings: Settings) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/assignees":
                data: list[dict[str, Any]] = self._assignees()
            elif path == "/issues":
                data = self._issues()
            elif path == "/worklogs":
                data = self._worklogs()
            elif path == "/overhead":
                data = self._overhead()
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _assignees(self) -> list[dict[str, Any]]:
            with get_conn(settings.db_path) as conn:
                rows = get_assignees_with_cost(conn)
            return [
                {
                    "display_name": row["display_name"],
                    "issue_count": row["issue_count"],
                    "man_days": row["man_days"],
                    "cost_eur": row["cost_eur"],
                    "rate_eur": row["rate_eur"],
                }
                for row in rows
            ]

        def _issues(self) -> list[dict[str, Any]]:
            with get_conn(settings.db_path) as conn:
                rows = get_issues_with_cost(conn)
            return [
                {
                    "issue_key": row["issue_key"],
                    "project_key": row["project_key"],
                    "issue_summary": row["issue_summary"],
                    "hours": row["hours"],
                    "cost_eur": row["cost_eur"],
                }
                for row in rows
            ]

        def _worklogs(self) -> list[dict[str, Any]]:
            with get_conn(settings.db_path) as conn:
                rows = conn.execute(
                    """SELECT worklog_id, issue_key, project_key, issue_summary,
                              author_display_name, assignee_display_name,
                              ROUND(time_spent_seconds / 3600.0, 2) AS hours,
                              started
                       FROM worklogs ORDER BY started DESC"""
                ).fetchall()
            return [{k: row[k] for k in row.keys()} for row in rows]  # type: ignore[union-attr]

        def _overhead(self) -> list[dict[str, Any]]:
            with get_conn(settings.db_path) as conn:
                rows = get_overhead_breakdown(conn)
            return [
                {
                    "display_name": row["display_name"],
                    "category": row["category"],
                    "total_hours": row["total_hours"],
                }
                for row in rows
            ]

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # suppress per-request access logs

    return _Handler


def start_server(settings: Settings) -> HTTPServer:
    """Start the JSON API server in a daemon thread. Returns the server instance."""
    server = HTTPServer(("localhost", settings.api_port), _make_handler(settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
