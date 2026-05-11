# jira-cost-tracker

A Python daemon that fetches Jira worklogs, computes cost per author using configurable hourly rates, and presents results in an interactive terminal UI with Excel export.

## Features

- **Scheduled sync** — runs automatically every hour during working hours (09:00–12:00 and 14:00–18:00)
- **Manual sync** — trigger a one-off sync from the CLI or from within the TUI
- **Interactive TUI** — four-tab Textual interface showing costs by issue, by assignee, editable rates, and sync history
- **Excel export** — three-sheet workbook (By Issue, By Assignee, raw Worklogs)
- **Multi-project** — configure multiple Jira project keys, all synced together
- **Live rate editing** — change an hourly rate and all historical costs recalculate instantly (cost is never stored, always computed)
- **SQLite storage** — zero infrastructure, WAL mode for safe concurrent access by daemon and TUI

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A Jira Cloud account with API token access

## Installation

```bash
git clone git@github.com:pandore-associates/jira-cost-tracker.git
cd jira-cost-tracker
uv sync
```

## Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

```env
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@your-org.com
JIRA_API_TOKEN=your_api_token_here
JIRA_PROJECTS=CSP,OTHER          # comma-separated project keys
DB_PATH=./cost_tracker.db        # SQLite database path
EXPORT_DIR=./exports             # Excel output directory
```

To generate a Jira API token: **Jira** → Account Settings → Security → [Create and manage API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).

## Usage

### One-off sync

```bash
tracker sync
# Syncing…
# Done. 47 worklogs synced.
```

### Scheduled daemon

Runs `tracker sync` automatically at 09:00, 10:00, 11:00, 12:00, 14:00, 15:00, 16:00, 17:00, and 18:00 every day.

```bash
tracker daemon
```

Run it in the background or as a system service. Press `Ctrl-C` to stop.

### Interactive TUI

```bash
tracker tui
```

| Key | Action |
|-----|--------|
| `S` | Sync now (runs in background thread) |
| `E` | Export to Excel |
| `Q` | Quit |
| `Tab` / `Shift-Tab` | Switch tabs |
| `↑` / `↓` | Navigate rows |
| `Enter` (in Rates tab) | Edit hourly rate |
| `Esc` | Cancel rate edit |

**Tabs:**

- **By Issue** — cost and hours aggregated per Jira issue, sorted by cost descending
- **By Assignee** — cost and hours per author; people with no rate set shown with `— not set`
- **Rates** — inline-editable hourly rates (€/h); authors auto-discovered on first sync
- **Sync Log** — history of sync runs with status, worklog count, and error messages

The TUI refreshes automatically every 5 seconds when the daemon is running alongside it.

### Export to Excel

```bash
tracker export
# Exported to ./exports/cost_2026-05-11_10-30.xlsx
```

The workbook contains three sheets:

| Sheet | Contents |
|-------|----------|
| **By Issue** | KEY, SUMMARY, PROJECT, HOURS, COST (€) |
| **By Assignee** | ASSIGNEE, ISSUES, HOURS, COST (€), RATE (€/h) |
| **Worklogs** | Raw worklog rows with all fields |

## How costs are calculated

```
cost = time_spent_seconds / 3600 × rate_eur
```

Cost is **never stored** in the database — it is computed on the fly by joining `worklogs` with `hourly_rates` at query time. Editing a rate in the Rates tab instantly recalculates all historical costs for that author.

Authors are auto-discovered from worklog data on first sync. Navigate to the **Rates** tab in the TUI and press `Enter` on a row to set the hourly rate.

## Project structure

```
src/cost_tracker/
├── cli.py           # Typer CLI — daemon, sync, tui, export subcommands
├── config.py        # pydantic-settings, loads .env
├── db.py            # SQLite schema + all query functions
├── jira_client.py   # httpx — fetches issues + worklogs via Jira REST API v3
├── sync.py          # run_sync(): fetch → upsert worklogs → log sync_run
├── scheduler.py     # APScheduler daemon with cron triggers
├── exporter.py      # openpyxl — 3-sheet Excel export
└── tui/
    ├── app.py              # Textual App, TabbedContent, 5s DB poll
    └── widgets/
        ├── issues_tab.py     # DataTable sorted by cost desc
        ├── assignees_tab.py  # DataTable grouped by author
        ├── rates_tab.py      # Inline-editable DataTable with modal
        └── logs_tab.py       # sync_runs history
```

## Development

```bash
uv sync                        # install all dependencies
uv run pytest                  # run test suite (27 tests)
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy .                  # type check (strict)
```

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| Jira 4xx / 5xx / timeout | Logged to `sync_runs` as `status=error`; daemon continues and retries on next tick |
| Missing hourly rate | Worklog stored, cost shown as `— not set` — not an error |
| `JIRA_API_TOKEN` unset | `daemon` and `tui` fail fast on startup with a clear message |
| SQLite concurrent write | WAL mode + 10 s connection timeout |

## License

MIT
