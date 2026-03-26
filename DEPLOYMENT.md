# Event List Dashboard — Deployment Guide

A static HTML dashboard showing upcoming Birdhaus events with ticket sales and capacity data. It auto-refreshes every 2 hours via GitHub Actions and is hosted on GitHub Pages.

---

## How It Works

1. `generate.py` calls the Wix API to fetch upcoming events (next 60 days)
2. It builds a self-contained HTML dashboard at `docs/index.html`
3. GitHub Actions runs this on a 2-hour cron schedule
4. The updated HTML is committed and pushed automatically
5. GitHub Pages serves `docs/index.html` as a public webpage

---

## 1. Set Up GitHub Secrets (Environment Variables)

The app needs three Wix API credentials. In GitHub Actions, these are stored as **repository secrets**.

### Where to find the values

All three come from your Wix site dashboard / API settings:

| Secret Name       | What It Is                                    |
|-------------------|-----------------------------------------------|
| `WIX_API_KEY`     | OAuth JWT token for API authentication         |
| `WIX_SITE_ID`    | Your Wix site's unique identifier              |
| `WIX_ACCOUNT_ID` | Your Wix account identifier                    |

### Where to put them

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each of the three secrets above (name must match exactly)

These are referenced in `.github/workflows/update-dashboard.yml` lines 28–30:
```yaml
env:
  WIX_API_KEY: ${{ secrets.WIX_API_KEY }}
  WIX_SITE_ID: ${{ secrets.WIX_SITE_ID }}
  WIX_ACCOUNT_ID: ${{ secrets.WIX_ACCOUNT_ID }}
```

### For local development

Create a `.env` file in the project root (it's gitignored):
```
WIX_API_KEY=your_key_here
WIX_SITE_ID=your_site_id_here
WIX_ACCOUNT_ID=your_account_id_here
```

---

## 2. Enable GitHub Pages

This is how the dashboard becomes a shareable webpage.

1. Go to your GitHub repository
2. Click **Settings** → **Pages**
3. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
4. Click **Save**

After a minute or two, your dashboard will be live at:

```
https://<your-github-username>.github.io/<repo-name>/
```

---

## 3. Verify the GitHub Actions Workflow

The workflow is already configured at `.github/workflows/update-dashboard.yml`. It:

- Runs every 2 hours (`cron: '0 */2 * * *'`)
- Can also be triggered manually from the **Actions** tab
- Installs Python 3.12, dependencies, and the `birdhaus_data_pipeline` package
- Runs `python generate.py`
- Commits and pushes any changes to `docs/index.html` and `data/events.json`

### To trigger it manually

1. Go to the **Actions** tab in your repo
2. Select **"Update Dashboard"** from the left sidebar
3. Click **"Run workflow"** → **"Run workflow"**

### To check if it's working

- Look at the **Actions** tab for green checkmarks
- Open `data/events.json` in the repo — the `fetched_at` timestamp should be recent
- Visit the GitHub Pages URL — the footer shows when data was last fetched

---

## 4. Share the Dashboard

### Public link (GitHub Pages)

Share the GitHub Pages URL directly:
```
https://<your-github-username>.github.io/<repo-name>/
```

Anyone with the link can view it — no login required. It supports light and dark mode automatically based on the viewer's system settings.

### Within your org

- **Bookmark it** — the URL never changes, and the content auto-updates
- **Embed it** — the page is a single self-contained HTML file, so it works in iframes
- **Slack/email** — just share the link; it loads instantly with no auth wall

### Custom domain (optional)

If you want a friendlier URL:
1. Go to **Settings** → **Pages** → **Custom domain**
2. Enter your domain (e.g., `events.yourdomain.com`)
3. Add a CNAME record in your DNS pointing to `<username>.github.io`

---

## 5. Local Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ../birdhaus_data_pipeline  # or: pip install birdhaus-data-pipeline

# Set credentials (or use a .env file)
export WIX_API_KEY="..."
export WIX_SITE_ID="..."
export WIX_ACCOUNT_ID="..."

# Generate the dashboard
python generate.py
```

Output:
- `docs/index.html` — the dashboard
- `data/events.json` — cached event data with timestamp

Open `docs/index.html` in a browser to preview locally.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Workflow fails with auth errors | Check that all 3 secrets are set correctly in Settings → Secrets → Actions |
| Dashboard page is 404 | Enable GitHub Pages (Settings → Pages → source: `main`, folder: `/docs`) |
| Dashboard shows no events | Verify Wix credentials are valid and the site has upcoming ticketed events |
| Workflow runs but nothing updates | Check the Actions log — if there are no event changes, it skips the commit |
| `birdhaus_data_pipeline` not found | Ensure the package is published to PyPI or available in the expected relative path |

To debug, check the **Actions** tab → click the failed run → expand each step to see logs.
