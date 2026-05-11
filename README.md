# jira-cost-tracker

Fetches Jira worklogs, computes cost per author, presents results in a TUI, and exports to Excel.

## Setup

```bash
cp .env.example .env   # fill in credentials
uv sync
```

## Usage

```bash
tracker daemon   # run scheduled sync (09-12, 14-18 hourly)
tracker sync     # one-off sync now
tracker tui      # open interactive TUI
tracker export   # export to Excel
```
