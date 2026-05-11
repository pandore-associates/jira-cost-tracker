import httpx
import pytest
import respx

from cost_tracker.jira_client import JiraClient, WorklogEntry


@pytest.fixture
def client() -> JiraClient:
    return JiraClient("https://example.atlassian.net", "user@example.com", "token")


@respx.mock
def test_get_worklogs_returns_entries(client: JiraClient) -> None:
    respx.post("https://example.atlassian.net/rest/api/3/issue/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "issues": [{"key": "CSP-1", "fields": {"summary": "Test issue"}}],
                "total": 1,
            },
        )
    )
    respx.get("https://example.atlassian.net/rest/api/3/issue/CSP-1/worklog").mock(
        return_value=httpx.Response(
            200,
            json={
                "worklogs": [
                    {
                        "id": "wl1",
                        "author": {"accountId": "acc1", "displayName": "Alice"},
                        "timeSpentSeconds": 3600,
                        "started": "2026-05-11T09:00:00.000+0000",
                    }
                ]
            },
        )
    )

    result = client.get_worklogs_for_project("CSP")

    assert len(result) == 1
    assert result[0].worklog_id == "wl1"
    assert result[0].issue_key == "CSP-1"
    assert result[0].project_key == "CSP"
    assert result[0].author_account_id == "acc1"
    assert result[0].time_spent_seconds == 3600


@respx.mock
def test_get_worklogs_raises_on_auth_error(client: JiraClient) -> None:
    respx.post("https://example.atlassian.net/rest/api/3/issue/search").mock(
        return_value=httpx.Response(401, json={"message": "Unauthorized"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.get_worklogs_for_project("CSP")


@respx.mock
def test_get_worklogs_paginates(client: JiraClient) -> None:
    respx.post("https://example.atlassian.net/rest/api/3/issue/search").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "issues": [{"key": "CSP-1", "fields": {"summary": "Issue 1"}}],
                    "total": 2,
                },
            ),
            httpx.Response(
                200,
                json={
                    "issues": [{"key": "CSP-2", "fields": {"summary": "Issue 2"}}],
                    "total": 2,
                },
            ),
        ]
    )
    respx.get("https://example.atlassian.net/rest/api/3/issue/CSP-1/worklog").mock(
        return_value=httpx.Response(200, json={"worklogs": []})
    )
    respx.get("https://example.atlassian.net/rest/api/3/issue/CSP-2/worklog").mock(
        return_value=httpx.Response(200, json={"worklogs": []})
    )

    result = client.get_worklogs_for_project("CSP")
    assert result == []  # no worklogs, but both pages were fetched


@respx.mock
def test_issue_with_no_worklogs(client: JiraClient) -> None:
    respx.post("https://example.atlassian.net/rest/api/3/issue/search").mock(
        return_value=httpx.Response(
            200,
            json={"issues": [{"key": "CSP-1", "fields": {"summary": "No work"}}], "total": 1},
        )
    )
    respx.get("https://example.atlassian.net/rest/api/3/issue/CSP-1/worklog").mock(
        return_value=httpx.Response(200, json={"worklogs": []})
    )
    assert client.get_worklogs_for_project("CSP") == []
