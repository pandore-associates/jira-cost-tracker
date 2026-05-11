from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger


@dataclass
class WorklogEntry:
    worklog_id: str
    issue_key: str
    project_key: str
    issue_summary: str
    author_account_id: str
    author_display_name: str
    time_spent_seconds: int
    started: str


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(email, api_token)

    def get_worklogs_for_project(self, project_key: str) -> list[WorklogEntry]:
        issues = self._get_all_issues(project_key)
        logger.info(f"Found {len(issues)} issues in {project_key}")
        result: list[WorklogEntry] = []
        for issue in issues:
            wls = self._get_issue_worklogs(issue)
            if wls:
                logger.debug(f"  {issue['key']}: {len(wls)} worklog(s)")
            result.extend(wls)
        return result

    def _get_all_issues(self, project_key: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        next_page_token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": f"project={project_key}",
                "fields": ["summary"],
                "maxResults": 100,
            }
            if next_page_token is not None:
                body["nextPageToken"] = next_page_token
            resp = httpx.post(
                f"{self._base_url}/rest/api/3/search/jql",
                auth=self._auth,
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            issues.extend(data["issues"])
            if data.get("isLast", True):
                break
            next_page_token = data.get("nextPageToken")
            if next_page_token is None:
                break
        return issues

    def _get_issue_worklogs(self, issue: dict[str, Any]) -> list[WorklogEntry]:
        issue_key: str = issue["key"]
        project_key = issue_key.split("-")[0]
        summary: str = issue["fields"]["summary"]
        resp = httpx.get(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/worklog",
            auth=self._auth,
            timeout=30,
        )
        resp.raise_for_status()
        return [
            WorklogEntry(
                worklog_id=str(w["id"]),
                issue_key=issue_key,
                project_key=project_key,
                issue_summary=summary,
                author_account_id=w["author"]["accountId"],
                author_display_name=w["author"]["displayName"],
                time_spent_seconds=int(w["timeSpentSeconds"]),
                started=w["started"],
            )
            for w in resp.json().get("worklogs", [])
        ]
