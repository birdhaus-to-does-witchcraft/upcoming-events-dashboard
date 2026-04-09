"""
Generate a static HTML dashboard of upcoming Birdhaus events.

Fetches data from Wix (via data_fetcher.py), builds a self-contained HTML
page with table + calendar views, and writes it to docs/index.html.

Run manually:  python generate.py
"""

import base64
import calendar as cal_mod
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, date, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from data_fetcher import fetch_upcoming_events

# ╔══════════════════════════════════════════════════════════════════╗
# ║  GUEST LIST PASSWORD CONFIG                                     ║
# ║  Change these values to set the passwords for downloading       ║
# ║  guest lists. The env var GUEST_LIST_PASSWORD overrides          ║
# ║  GLOBAL_PASSWORD when set (useful for CI / GitHub Secrets).     ║
# ╚══════════════════════════════════════════════════════════════════╝

# Global password: grants access to ALL event guest lists (core team)
GLOBAL_PASSWORD = "changeme2"

# Per-event passwords: grants access to ONE specific event's guest list.
# Keys must match the event title exactly as shown in the dashboard.
EVENT_PASSWORDS = {
    # "Board at Birdhaus": "boardnight2026",
}

def _get_global_password():
    return os.getenv("GUEST_LIST_PASSWORD", GLOBAL_PASSWORD)


def encrypt_for_download(plaintext: str, password: str) -> str:
    """AES-256-GCM encrypt plaintext with a password. Returns base64(salt+nonce+ciphertext)."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000, dklen=32)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(salt + nonce + ciphertext).decode()


DOCS_DIR = Path(__file__).parent / "docs"
OUTPUT_FILE = DOCS_DIR / "index.html"
DATA_FILE = Path(__file__).parent / "data" / "events.json"


def _load_env_file(env_path: Path):
    try:
        exists = env_path.exists()
    except OSError:
        return {"loaded": False, "set_count": 0}

    if not exists:
        return {"loaded": False, "set_count": 0}

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"loaded": False, "set_count": 0}

    set_count = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and not os.getenv(key):
            parsed_value = value.strip()
            # Support inline comments in .env lines like: KEY=value # note
            # while preserving hashes that are part of quoted values.
            if (
                len(parsed_value) >= 2
                and parsed_value[0] == parsed_value[-1]
                and parsed_value[0] in {'"', "'"}
            ):
                parsed_value = parsed_value[1:-1]
            elif " #" in parsed_value:
                parsed_value = parsed_value.split(" #", 1)[0].strip()
            os.environ[key] = parsed_value
            set_count += 1
    return {"loaded": True, "set_count": set_count}


def _ensure_wix_env():
    if os.getenv("WIX_API_KEY") and os.getenv("WIX_SITE_ID") and os.getenv("WIX_ACCOUNT_ID"):
        return

    candidates = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / "birdhaus_data_pipeline" / ".env",
    ]
    for candidate in candidates:
        _load_env_file(candidate)


def fetch_and_cache():
    """Fetch events from Wix and save to local JSON cache."""
    DATA_FILE.parent.mkdir(exist_ok=True)
    _ensure_wix_env()
    print(f"[{datetime.now():%H:%M:%S}] Fetching events from Wix...")

    df = fetch_upcoming_events(days_ahead=60)

    all_events = df.to_dict(orient="records") if not df.empty else []
    fetched_at = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).isoformat()

    cache_events = [{k: v for k, v in ev.items() if k != "Guests"} for ev in all_events]
    cache_payload = {"fetched_at": fetched_at, "events": cache_events}
    DATA_FILE.write_text(json.dumps(cache_payload, default=str), encoding="utf-8")
    print(f"[{datetime.now():%H:%M:%S}] Saved {len(cache_events)} events to {DATA_FILE}")

    return {"fetched_at": fetched_at, "events": all_events}


def format_date(day, raw_date):
    try:
        d = datetime.strptime(str(raw_date), "%Y-%m-%d")
        short_day = day[:3] if day else ""
        return f"{short_day}, {d.strftime('%b %-d')}"
    except (ValueError, TypeError):
        return f"{day}, {raw_date}" if day else str(raw_date)


def to_12h(time_str):
    if not time_str:
        return ""
    try:
        t = datetime.strptime(str(time_str), "%H:%M:%S")
        return t.strftime("%-I:%M %p")
    except (ValueError, TypeError):
        return str(time_str)


def capacity_class(cap_str):
    if "Unlimited" in str(cap_str):
        return "cap-unlimited"
    try:
        parts = str(cap_str).split("/")
        if len(parts) == 2:
            sold = int(parts[0].strip())
            total = int(parts[1].strip())
            ratio = sold / total if total > 0 else 0
            if ratio >= 1.0:
                return "cap-full"
            elif ratio >= 0.7:
                return "cap-high"
        return "cap-ok"
    except (ValueError, IndexError):
        return "cap-ok"


def build_html(events, fetched_at):
    """Build the complete HTML document from event data."""
    if not events:
        return build_empty_html()

    # Format display columns
    for ev in events:
        ev["DateFmt"] = format_date(ev.get("Day", ""), ev.get("Date", ""))
        ev["TimeFmt"] = to_12h(ev.get("Time", ""))

    # Build table rows
    global_pw = _get_global_password()
    rows_html = ""
    for ev in events:
        cap_cls = capacity_class(ev.get("Capacity", ""))
        event_url = str(ev.get("EventUrl", "")).strip()

        guest_list = ev.get("Guests", [])
        if not isinstance(guest_list, list):
            guest_list = []
        guest_json = json.dumps(guest_list)
        enc_global = encrypt_for_download(guest_json, global_pw)

        event_title = str(ev.get("Event", ""))
        event_pw = EVENT_PASSWORDS.get(event_title)
        enc_event = encrypt_for_download(guest_json, event_pw) if event_pw else ""

        data_attrs = f' data-guests-global="{enc_global}"'
        if enc_event:
            data_attrs += f' data-guests-event="{enc_event}"'
        data_attrs += f' data-event-name="{escape(event_title, quote=True)}"'

        download_btn = (
            f'<button class="event-icon" onclick="promptGuestDownload(this)" title="Download guest list">'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
            f'<polyline points="7 10 12 15 17 10"/>'
            f'<line x1="12" y1="15" x2="12" y2="3"/>'
            f'</svg></button>'
        )

        url_icons = ""
        if event_url:
            escaped_url = escape(event_url, quote=True)
            url_icons = (
                f'<a href="{escaped_url}" target="_blank" rel="noopener" class="event-icon" title="Open event page">'
                f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
                f'<polyline points="15 3 21 3 21 9"/>'
                f'<line x1="10" y1="14" x2="21" y2="3"/>'
                f'</svg></a>'
                f'<button class="event-icon" onclick="navigator.clipboard.writeText(\'{escaped_url}\');this.classList.add(\'copied\');setTimeout(()=>this.classList.remove(\'copied\'),1500)" title="Copy link">'
                f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
                f'<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
                f'</svg></button>'
            )

        link_icons = f'<span class="event-links">{url_icons}{download_btn}</span>'
        rows_html += f"""<tr{data_attrs}>
<td class="cell cell-event" data-label="Event">{escape(event_title)}{link_icons}</td>
<td class="cell cell-meta" data-label="Date">{escape(str(ev['DateFmt']))}<span class="time-inline"> &middot; {escape(str(ev['TimeFmt']))}</span></td>
<td class="cell cell-meta cell-time" data-label="Time">{escape(str(ev['TimeFmt']))}</td>
<td class="cell cell-tickets" data-label="Tickets Sold">{escape(str(ev['Tickets']))}</td>
<td class="cell {cap_cls}" data-label="Capacity">{escape(str(ev['Capacity']))}</td>
</tr>"""

    # Build calendar
    events_by_date = defaultdict(list)
    for ev in events:
        events_by_date[ev["Date"]].append({
            "name": ev["Event"],
            "time": ev["TimeFmt"],
        })

    all_dates = []
    for ev in events:
        try:
            all_dates.append(datetime.strptime(str(ev["Date"]), "%Y-%m-%d").date())
        except (ValueError, TypeError):
            pass

    if not all_dates:
        months_to_show = []
    else:
        today = date.today()
        min_date = min(min(all_dates), today)
        max_date = max(all_dates)
        months_to_show = []
        ym = (min_date.year, min_date.month)
        end_ym = (max_date.year, max_date.month)
        while ym <= end_ym:
            months_to_show.append(ym)
            if ym[1] == 12:
                ym = (ym[0] + 1, 1)
            else:
                ym = (ym[0], ym[1] + 1)

    cal = cal_mod.Calendar(firstweekday=0)
    today_iso = date.today().isoformat()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    cal_html = ""
    for year, month in months_to_show:
        month_name = cal_mod.month_name[month]
        cal_html += f'<div class="cal-month"><h3 class="cal-month-title">{month_name} {year}</h3>'
        cal_html += '<table class="cal-grid"><thead><tr>'
        for dn in day_names:
            cal_html += f'<th class="cal-dayname">{dn}</th>'
        cal_html += '</tr></thead><tbody>'

        weeks = cal.monthdayscalendar(year, month)
        for week in weeks:
            cal_html += '<tr>'
            for day_num in week:
                if day_num == 0:
                    cal_html += '<td class="cal-cell cal-empty"></td>'
                else:
                    d_iso = f"{year}-{month:02d}-{day_num:02d}"
                    is_today = "cal-today" if d_iso == today_iso else ""
                    day_events = events_by_date.get(d_iso, [])
                    events_markup = ""
                    for ev in day_events:
                        short_name = ev["name"][:22] + ("..." if len(ev["name"]) > 22 else "")
                        events_markup += f'<div class="cal-event">{escape(short_name)}<br><span class="cal-event-time">{escape(ev["time"])}</span></div>'
                    has_event = "cal-has-event" if day_events else ""
                    cal_html += f'<td class="cal-cell {is_today} {has_event}"><div class="cal-day-num">{day_num}</div>{events_markup}</td>'
            cal_html += '</tr>'

        cal_html += '</tbody></table></div>'

    # Format fetched_at timestamp
    if fetched_at:
        try:
            ft = datetime.fromisoformat(fetched_at)
            fetched_display = ft.strftime("%B %-d, %Y at %-I:%M %p")
        except (ValueError, TypeError):
            fetched_display = fetched_at
    else:
        fetched_display = "unknown"

    count = len(events)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Birdhaus Upcoming Events</title>
<style>
  :root {{
    --bg: #ffffff;
    --bg-header: #f5f5f5;
    --text: #1a1a1a;
    --text-soft: #555;
    --text-muted: #999;
    --border: #e8e8e8;
    --hover: #fafafa;
    --cap-ok: #2e8b57;
    --cap-high: #d4880f;
    --cap-full: #d9534f;
    --cap-muted: #888;
    --cal-event-bg: #e3f2fd;
    --cal-event-text: #1565c0;
    --cal-today-bg: #fff8e1;
    --cal-empty: transparent;
  }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1a1a1a;
      --bg-header: #242424;
      --text: #e8e4e0;
      --text-soft: #bbb5ae;
      --text-muted: #777;
      --border: #333;
      --hover: #222;
      --cap-ok: #5cb85c;
      --cap-high: #e6a23c;
      --cap-full: #e74c3c;
      --cap-muted: #777;
      --cal-event-bg: #1e3a5f;
      --cal-event-text: #90caf9;
      --cal-today-bg: #3e3520;
      --cal-empty: transparent;
    }}
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: var(--text);
    padding: 2rem 1.5rem;
  }}

  .page-title {{
    font-size: 2rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.3rem;
  }}

  .page-sub {{
    font-size: 1.05rem;
    color: var(--text-soft);
    margin-bottom: 1.8rem;
  }}

  /* ── Table ── */

  .bh-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 1.05rem;
  }}

  .bh-table th {{
    background: var(--bg-header);
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    padding: 10px 16px;
    border-bottom: 2px solid var(--border);
    text-align: left;
  }}

  .cell {{
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    color: var(--text-soft);
    vertical-align: middle;
  }}

  .cell-event {{ font-weight: 600; color: var(--text); }}
  .cell-meta {{ color: var(--text-soft); }}

  .cap-ok {{ color: var(--cap-ok); font-weight: 500; }}
  .cap-high {{ color: var(--cap-high); font-weight: 500; }}
  .cap-full {{ color: var(--cap-full); font-weight: 600; }}
  .cap-unlimited {{ color: var(--cap-muted); }}

  .bh-table tbody tr:hover .cell {{ background: var(--hover); }}
  .bh-table tbody tr:last-child .cell {{ border-bottom: none; }}

  /* ── Calendar ── */

  .cal-section {{
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 2px solid var(--border);
  }}

  .cal-section-title {{
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 1.5rem;
  }}

  .cal-month {{ margin-bottom: 2.5rem; }}

  .cal-month-title {{
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.6rem;
  }}

  .cal-grid {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}

  .cal-dayname {{
    padding: 8px 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    text-align: center;
    border-bottom: 1px solid var(--border);
  }}

  .cal-cell {{
    height: 90px;
    vertical-align: top;
    padding: 6px;
    border: 1px solid var(--border);
    background: var(--bg);
  }}

  .cal-empty {{
    background: var(--cal-empty);
    border-color: transparent;
  }}

  .cal-today {{ background: var(--cal-today-bg); }}

  .cal-day-num {{
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 4px;
  }}

  .cal-today .cal-day-num {{ font-weight: 700; color: var(--text); }}

  .cal-event {{
    background: var(--cal-event-bg);
    color: var(--cal-event-text);
    padding: 3px 6px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-bottom: 3px;
    line-height: 1.3;
    overflow: hidden;
  }}

  .cal-event-time {{
    font-weight: 400;
    font-size: 0.7rem;
    opacity: 0.8;
  }}

  /* ── Event link icons ── */

  .event-links {{
    display: inline-flex;
    gap: 6px;
    margin-left: 8px;
    vertical-align: middle;
  }}

  .event-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
    text-decoration: none;
    transition: color 0.15s;
  }}

  .event-icon:hover {{ color: var(--text); }}

  .event-icon.copied {{ color: var(--cap-ok); }}

  .time-inline {{ display: none; }}

  /* ── Mobile: tablet / large phone ── */

  @media (max-width: 768px) {{
    body {{ padding: 1rem 0.75rem; }}

    .page-title {{ font-size: 1.5rem; }}
    .page-sub {{ font-size: 0.9rem; margin-bottom: 1.2rem; }}

    .bh-table {{ font-size: 0.85rem; }}

    .bh-table th {{ padding: 8px 10px; font-size: 0.7rem; }}
    .cell {{ padding: 8px 10px; }}

    .cell-event {{ max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

    /* Hide separate Time column, show inline */
    .bh-table th:nth-child(3),
    .cell-time {{ display: none; }}
    .time-inline {{ display: inline; }}

    /* Calendar adjustments */
    .cal-cell {{ height: 60px; padding: 4px; }}
    .cal-event {{ font-size: 0.65rem; }}
    .cal-event-time {{ font-size: 0.6rem; }}
    .cal-day-num {{ font-size: 0.75rem; }}
  }}

  /* ── Mobile: small phone ── */

  @media (max-width: 480px) {{
    body {{ padding: 0.75rem 0.5rem; }}

    .page-title {{ font-size: 1.3rem; }}

    /* Card layout */
    .bh-table thead {{ display: none; }}
    .bh-table tbody tr {{
      display: block;
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 0.75rem;
      padding: 10px 12px;
    }}
    .bh-table tbody tr:hover .cell {{ background: none; }}

    .cell {{
      display: block;
      border-bottom: none;
      padding: 3px 0;
    }}
    .cell::before {{
      content: attr(data-label);
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.4px;
      margin-right: 8px;
      min-width: 70px;
    }}
    .cell-event {{
      max-width: none;
      white-space: normal;
      font-size: 0.95rem;
      padding-bottom: 4px;
    }}
    .cell-event::before {{ display: none; }}

    /* Keep Time hidden in card view (shown inline with date) */
    .cell-time {{ display: none; }}
    .time-inline {{ display: inline; }}

    /* Calendar small phone */
    .cal-cell {{ height: 45px; padding: 2px; }}
    .cal-event {{ font-size: 0.6rem; padding: 2px 3px; }}
    .cal-event-time {{ display: none; }}
    .cal-dayname {{ font-size: 0.65rem; padding: 4px 2px; }}
    .cal-month-title {{ font-size: 1rem; }}
  }}

  /* ── Footer ── */

  .footer-text {{
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }}

  /* ── Password modal ── */

  .pw-overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 1000;
    align-items: center;
    justify-content: center;
  }}
  .pw-overlay.active {{ display: flex; }}

  .pw-modal {{
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.8rem;
    width: 340px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25);
  }}

  .pw-modal h3 {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.3rem;
  }}

  .pw-modal .pw-event-name {{
    font-size: 0.85rem;
    color: var(--text-soft);
    margin-bottom: 1rem;
  }}

  .pw-modal input {{
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.95rem;
    background: var(--bg);
    color: var(--text);
    outline: none;
    transition: border-color 0.15s;
  }}
  .pw-modal input:focus {{ border-color: var(--cap-ok); }}
  .pw-modal input.pw-error {{ border-color: var(--cap-full); }}

  .pw-modal .pw-err-msg {{
    font-size: 0.8rem;
    color: var(--cap-full);
    margin-top: 0.4rem;
    min-height: 1.2em;
  }}

  .pw-modal .pw-actions {{
    display: flex;
    gap: 8px;
    margin-top: 1rem;
    justify-content: flex-end;
  }}

  .pw-modal button {{
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--bg-header);
    color: var(--text);
    transition: background 0.15s;
  }}
  .pw-modal button:hover {{ background: var(--hover); }}

  .pw-modal .pw-submit {{
    background: var(--cap-ok);
    color: #fff;
    border-color: var(--cap-ok);
  }}
  .pw-modal .pw-submit:hover {{ opacity: 0.9; background: var(--cap-ok); }}
</style>
</head>
<body>

<div class="page-title">Birdhaus Upcoming Events</div>
<div class="page-sub">{count} events in the next 2 months</div>

<table class="bh-table">
<thead><tr>
  <th>Event</th>
  <th>Date</th>
  <th>Time</th>
  <th>Tickets Sold</th>
  <th>Capacity</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>

<div class="cal-section">
  <div class="cal-section-title">Calendar</div>
  {cal_html}
</div>

<p class="footer-text">Data from {fetched_display}</p>

<div class="pw-overlay" id="pwOverlay">
  <div class="pw-modal">
    <h3>Download Guest List</h3>
    <div class="pw-event-name" id="pwEventName"></div>
    <form id="pwForm" onsubmit="return handlePwSubmit(event)">
      <input type="password" id="pwInput" placeholder="Enter password" autocomplete="off" />
      <div class="pw-err-msg" id="pwErr"></div>
      <div class="pw-actions">
        <button type="button" onclick="closePwModal()">Cancel</button>
        <button type="submit" class="pw-submit">Download</button>
      </div>
    </form>
  </div>
</div>

<script>
(function(){{
  var activeRow=null;

  function showModal(){{
    document.getElementById('pwInput').value='';
    document.getElementById('pwInput').classList.remove('pw-error');
    document.getElementById('pwErr').textContent='';
    document.getElementById('pwOverlay').classList.add('active');
    setTimeout(function(){{document.getElementById('pwInput').focus();}},50);
  }}

  window.promptGuestDownload=function(btn){{
    activeRow=btn.closest('tr');
    var name=activeRow.getAttribute('data-event-name')||'Event';
    document.getElementById('pwEventName').textContent=name;
    var saved=sessionStorage.getItem('_gl_pw');
    if(saved){{tryDecryptAndDownload(saved,true);return;}}
    showModal();
  }};

  window.closePwModal=function(){{
    document.getElementById('pwOverlay').classList.remove('active');
    activeRow=null;
  }};

  window.handlePwSubmit=function(e){{
    e.preventDefault();
    var pw=document.getElementById('pwInput').value;
    if(!pw)return false;
    tryDecryptAndDownload(pw,false);
    return false;
  }};

  async function deriveKey(password,salt){{
    var enc=new TextEncoder();
    var km=await crypto.subtle.importKey('raw',enc.encode(password),'PBKDF2',false,['deriveKey']);
    return crypto.subtle.deriveKey({{name:'PBKDF2',salt:salt,iterations:100000,hash:'SHA-256'}},km,{{name:'AES-GCM',length:256}},false,['decrypt']);
  }}

  async function decryptBlob(b64,password){{
    var raw=Uint8Array.from(atob(b64),function(c){{return c.charCodeAt(0);}});
    var salt=raw.slice(0,16);
    var nonce=raw.slice(16,28);
    var ct=raw.slice(28);
    var key=await deriveKey(password,salt);
    var dec=await crypto.subtle.decrypt({{name:'AES-GCM',iv:nonce}},key,ct);
    return new TextDecoder().decode(dec);
  }}

  async function tryDecryptAndDownload(pw,fromCache){{
    if(!activeRow)return;
    var globalBlob=activeRow.getAttribute('data-guests-global');
    var eventBlob=activeRow.getAttribute('data-guests-event');
    var eventName=activeRow.getAttribute('data-event-name')||'guests';
    var decrypted=null;
    if(globalBlob){{try{{decrypted=await decryptBlob(globalBlob,pw);}}catch(_){{}}}}
    if(!decrypted&&eventBlob){{try{{decrypted=await decryptBlob(eventBlob,pw);}}catch(_){{}}}}
    if(decrypted){{
      sessionStorage.setItem('_gl_pw',pw);
      downloadCsv(decrypted,eventName);
      closePwModal();
    }}else if(fromCache){{
      sessionStorage.removeItem('_gl_pw');
      showModal();
    }}else{{
      document.getElementById('pwInput').classList.add('pw-error');
      document.getElementById('pwErr').textContent='Incorrect password';
    }}
  }}

  function downloadCsv(jsonStr,eventName){{
    var guests=JSON.parse(jsonStr);
    var lines=['Name,Ticket Type'];
    guests.forEach(function(g){{
      var n=(g.name||'').replace(/"/g,'""');
      var t=(g.ticket_type||'').replace(/"/g,'""');
      lines.push('"'+n+'","'+t+'"');
    }});
    var csv=lines.join('\\r\\n');
    var blob=new Blob([csv],{{type:'text/csv;charset=utf-8;'}});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;
    a.download=eventName.replace(/[^a-zA-Z0-9 _-]/g,'').replace(/ +/g,'_')+'_guests.csv';
    document.body.appendChild(a);a.click();
    setTimeout(function(){{document.body.removeChild(a);URL.revokeObjectURL(url);}},100);
  }}

  document.getElementById('pwOverlay').addEventListener('click',function(e){{
    if(e.target===this)closePwModal();
  }});
}})();
</script>

</body>
</html>"""


def build_empty_html():
    """Build an HTML page for when there are no events."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Birdhaus Upcoming Events</title>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    padding: 2rem; color: #555; text-align: center; margin-top: 4rem;
  }
</style>
</head>
<body>
<h1>Birdhaus Upcoming Events</h1>
<p>No upcoming events found in the next 2 months.</p>
</body>
</html>"""


def main():
    payload = fetch_and_cache()
    events = payload.get("events", [])
    fetched_at = payload.get("fetched_at")
    events = [
        ev for ev in events
        if str(ev.get("Capacity", "")).strip().lower() != "unknown"
    ]
    html = build_html(events, fetched_at)

    DOCS_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"[{datetime.now():%H:%M:%S}] Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
