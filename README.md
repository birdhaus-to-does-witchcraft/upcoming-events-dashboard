# Event List Dashboard

A static HTML dashboard that displays upcoming Birdhaus events with ticket sales and capacity data, refreshed automatically every 30 minutes via GitHub Actions and hosted on GitHub Pages.

## What it does

- Pulls upcoming events (next 60 days) from the Wix API using the [`birdhaus_data_pipeline`](../birdhaus_data_pipeline)
- Fetches per-event ticket definitions (V3) and guest counts for accurate sold/capacity numbers
- Generates a self-contained HTML page (`docs/index.html`) with:
  - **Table view** — event name, date, time, tickets sold, and capacity with color-coded fill indicators (green/amber/red)
  - **Calendar view** — month grids with event markers
- Supports light and dark mode via `prefers-color-scheme`

## Project structure

```
event-list-dashboard/
├── generate.py          # Fetches data, builds HTML, writes docs/index.html
├── data_fetcher.py      # Wix API calls (events, tickets, guests)
├── requirements.txt     # Python dependencies
├── data/
│   └── events.json      # Cached event data (auto-generated)
├── docs/
│   └── index.html       # Dashboard output (served by GitHub Pages)
└── .github/
    └── workflows/
        └── update-dashboard.yml  # Scheduled refresh every 30 min
```

## Setup

### Prerequisites

- Python 3.12+
- The `birdhaus_data_pipeline` package installed (editable or from registry)
- Wix API credentials set as environment variables:
  - `WIX_API_KEY`
  - `WIX_SITE_ID`
  - `WIX_ACCOUNT_ID`

### Install

```bash
pip install -r requirements.txt
pip install -e ../birdhaus_data_pipeline  # or however the pipeline is available
```

### Run locally

```bash
python generate.py
```

This fetches live data from Wix, caches it to `data/events.json`, and writes the dashboard to `docs/index.html`. Open that file in a browser to view.

## Deployment

The GitHub Actions workflow (`.github/workflows/update-dashboard.yml`) runs on a 30-minute cron schedule and can also be triggered manually. It:

1. Installs dependencies and the data pipeline
2. Runs `generate.py` with Wix credentials from repository secrets
3. Commits and pushes `docs/index.html` and `data/events.json` if anything changed

Serve `docs/` with GitHub Pages to make the dashboard publicly accessible.
