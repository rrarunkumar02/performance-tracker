from __future__ import annotations

import html
import json
import os
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "team_tracker.db"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_KEY", ""
)


WEEKS = [
    {
        "name": "Week 0",
        "range": "0-3",
        "tasks": [
            "Bike competency",
            "P2E Level 2",
            "App setup - Teams",
            "App setup - Safety Culture",
            "App setup - Tanda",
            "Explaining the goal",
            "Store tour - Cut bench",
            "Store tour - Sauce bench",
            "Store tour - Make line",
            "Store tour - Side makeline",
            "Store tour - Drinks fridge",
            "Store tour - Dough area",
            "Store tour - Cool room",
            "Bringing the dough",
            "Arranging the cut bench",
            "Filling the makeline",
            "Filling the sides makeline",
            "Cut",
            "Counter order",
            "Saucing",
        ],
    },
    {
        "name": "Week 1",
        "range": "3-6",
        "tasks": [
            "Delivery time",
            "Cut time",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time",
            "Cut bench setup time",
            "Michael Mark",
            "Weekly Progress",
        ],
    },
    {
        "name": "Week 2",
        "range": "6-9",
        "tasks": [
            "Delivery time",
            "Cut time",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time",
            "Cut bench setup time",
            "Michael Mark",
            "Weekly Progress",
            "We spent $900 without super. Do we still need to continue with this person?",
        ],
    },
    {
        "name": "Week 3",
        "range": "9-12",
        "tasks": [
            "Delivery time",
            "Cut time",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time",
            "Cut bench setup time",
            "Michael Mark",
            "Weekly Progress",
        ],
    },
    {
        "name": "Week 4",
        "range": "12-15",
        "tasks": [
            "Delivery time",
            "Cut time",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time",
            "Cut bench setup time",
            "Weekly Progress",
            "Overall Score",
            "Final $1600 without super. Is this person fit for the store?",
        ],
    },
]

NUMBER_VALUE_TASKS = {
    "Delivery time",
    "Cut time",
    "Cut quiz",
    "Shift runners mark",
    "Counter order test",
    "Saucing time",
    "Cut bench setup time",
    "Michael Mark",
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def use_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_request(
    method: str,
    table: str,
    query: str = "",
    payload: object | None = None,
    prefer: str = "",
) -> list[dict[str, object]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if query:
        url = f"{url}?{query}"

    body = None
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=20) as response:
        response_body = response.read().decode("utf-8")
    if not response_body:
        return []
    return json.loads(response_body)


def init_db() -> None:
    if use_supabase():
        return

    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                member_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                need_to_eye_on TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        member_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(members)")
        }
        if "need_to_eye_on" not in member_columns:
            connection.execute(
                "ALTER TABLE members ADD COLUMN need_to_eye_on TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS member_tracking (
                tracking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                week_name TEXT NOT NULL,
                week_range TEXT NOT NULL,
                task_name TEXT NOT NULL,
                value_status TEXT NOT NULL DEFAULT '',
                conducted_by TEXT NOT NULL DEFAULT '',
                note_to_eye_on TEXT NOT NULL DEFAULT '',
                michael_mark TEXT NOT NULL DEFAULT '',
                shift_runner_mark TEXT NOT NULL DEFAULT '',
                weekly_progress TEXT NOT NULL DEFAULT '',
                overall_score TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(member_id, week_name, task_name),
                FOREIGN KEY(member_id) REFERENCES members(member_id)
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(member_tracking)")
        }
        if "note_to_eye_on" not in columns:
            connection.execute(
                "ALTER TABLE member_tracking ADD COLUMN note_to_eye_on TEXT NOT NULL DEFAULT ''"
            )
        if "michael_mark" not in columns:
            connection.execute(
                "ALTER TABLE member_tracking ADD COLUMN michael_mark TEXT NOT NULL DEFAULT ''"
            )
        if "shift_runner_mark" not in columns:
            connection.execute(
                "ALTER TABLE member_tracking ADD COLUMN shift_runner_mark TEXT NOT NULL DEFAULT ''"
            )
        if "weekly_progress" not in columns:
            connection.execute(
                "ALTER TABLE member_tracking ADD COLUMN weekly_progress TEXT NOT NULL DEFAULT ''"
            )
        if "overall_score" not in columns:
            connection.execute(
                "ALTER TABLE member_tracking ADD COLUMN overall_score TEXT NOT NULL DEFAULT ''"
            )


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_member(name: str) -> bool:
    clean_name = name.strip()
    if not clean_name:
        return False

    if use_supabase():
        supabase_request(
            "POST",
            "members",
            payload={"name": clean_name, "created_at": now_text()},
            prefer="return=minimal",
        )
        return True

    with get_connection() as connection:
        connection.execute(
            "INSERT INTO members (name, created_at) VALUES (?, ?)",
            (clean_name, now_text()),
        )
    return True


def get_members() -> list[sqlite3.Row]:
    if use_supabase():
        query = urlencode(
            {
                "select": "member_id,name,created_at",
                "order": "member_id.asc",
            }
        )
        return supabase_request("GET", "members", query)

    with get_connection() as connection:
        return list(
            connection.execute(
                "SELECT member_id, name, created_at FROM members ORDER BY member_id"
            )
        )


def get_member(member_id: int) -> sqlite3.Row | None:
    if use_supabase():
        query = urlencode(
            {
                "select": "member_id,name,need_to_eye_on,created_at",
                "member_id": f"eq.{member_id}",
                "limit": "1",
            }
        )
        rows = supabase_request("GET", "members", query)
        return rows[0] if rows else None

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT member_id, name, need_to_eye_on, created_at
            FROM members
            WHERE member_id = ?
            """,
            (member_id,),
        ).fetchone()


def ensure_tracking_rows(member_id: int) -> None:
    timestamp = now_text()
    if use_supabase():
        rows = []
        for week in WEEKS:
            for task in week["tasks"]:
                rows.append(
                    {
                        "member_id": member_id,
                        "week_name": week["name"],
                        "week_range": week["range"],
                        "task_name": task,
                        "updated_at": timestamp,
                    }
                )
        query = "on_conflict=member_id,week_name,task_name"
        supabase_request(
            "POST",
            "member_tracking",
            query,
            rows,
            "resolution=ignore-duplicates,return=minimal",
        )
        return

    with get_connection() as connection:
        for week in WEEKS:
            for task in week["tasks"]:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO member_tracking (
                        member_id, week_name, week_range, task_name, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (member_id, week["name"], week["range"], task, timestamp),
                )


def get_tracking(member_id: int) -> dict[tuple[str, str], sqlite3.Row]:
    ensure_tracking_rows(member_id)
    if use_supabase():
        query = urlencode(
            {
                "select": (
                    "tracking_id,member_id,week_name,week_range,task_name,"
                    "value_status,conducted_by,note_to_eye_on,michael_mark,"
                    "shift_runner_mark,weekly_progress,overall_score,updated_at"
                ),
                "member_id": f"eq.{member_id}",
                "order": "tracking_id.asc",
            }
        )
        rows = supabase_request("GET", "member_tracking", query)
        return {(row["week_name"], row["task_name"]): row for row in rows}

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT tracking_id, member_id, week_name, week_range, task_name,
                   value_status, conducted_by, note_to_eye_on, michael_mark,
                   shift_runner_mark, weekly_progress, overall_score, updated_at
            FROM member_tracking
            WHERE member_id = ?
            ORDER BY tracking_id
            """,
            (member_id,),
        ).fetchall()
    return {(row["week_name"], row["task_name"]): row for row in rows}


def parse_float(value: str) -> float | None:
    clean_value = value.strip()
    if not clean_value:
        return None
    try:
        return float(clean_value)
    except ValueError:
        return None


def format_average(values: list[float]) -> str:
    if not values:
        return ""
    average = sum(values) / len(values)
    return f"{average:.2f}".rstrip("0").rstrip(".")


def calculate_weekly_progress(
    form_data: dict[str, list[str]], tracking: dict[tuple[str, str], sqlite3.Row]
) -> dict[int, str]:
    weekly_progress_values = {}
    for week in WEEKS:
        marks = []
        weekly_progress_id = None
        for task in week["tasks"]:
            record = tracking.get((week["name"], task))
            if record is None:
                continue

            tracking_id = int(record["tracking_id"])
            if task == "Weekly Progress":
                weekly_progress_id = tracking_id
                continue

            if task not in NUMBER_VALUE_TASKS:
                continue

            form_value = form_data.get(
                f"value_{tracking_id}", [str(record["value_status"] or "")]
            )[0]
            number_value = parse_float(form_value)
            if number_value is not None:
                marks.append(number_value)

        if weekly_progress_id is not None:
            weekly_progress_values[weekly_progress_id] = format_average(marks)

    return weekly_progress_values


def save_tracking(member_id: int, form_data: dict[str, list[str]]) -> None:
    timestamp = now_text()
    need_to_eye_on = form_data.get("need_to_eye_on", [""])[0].strip()
    tracking = get_tracking(member_id)
    weekly_progress_values = calculate_weekly_progress(form_data, tracking)
    if use_supabase():
        member_query = urlencode({"member_id": f"eq.{member_id}"})
        supabase_request(
            "PATCH",
            "members",
            member_query,
            {"need_to_eye_on": need_to_eye_on},
            "return=minimal",
        )
        for key, values in form_data.items():
            if not key.startswith("value_"):
                continue

            tracking_id = int(key.replace("value_", "", 1))
            value_status = values[0].strip() if values else ""
            if tracking_id in weekly_progress_values:
                value_status = weekly_progress_values[tracking_id]
            conducted_values = form_data.get(f"conducted_{tracking_id}", [""])
            conducted_by = conducted_values[0].strip()
            query = urlencode(
                {
                    "tracking_id": f"eq.{tracking_id}",
                    "member_id": f"eq.{member_id}",
                }
            )
            supabase_request(
                "PATCH",
                "member_tracking",
                query,
                {
                    "value_status": value_status,
                    "conducted_by": conducted_by,
                    "updated_at": timestamp,
                },
                "return=minimal",
            )
        return

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE members
            SET need_to_eye_on = ?
            WHERE member_id = ?
            """,
            (need_to_eye_on, member_id),
        )
        for key, values in form_data.items():
            if not key.startswith("value_"):
                continue

            tracking_id = int(key.replace("value_", "", 1))
            value_status = values[0].strip() if values else ""
            if tracking_id in weekly_progress_values:
                value_status = weekly_progress_values[tracking_id]
            conducted_values = form_data.get(f"conducted_{tracking_id}", [""])
            conducted_by = conducted_values[0].strip()
            michael_mark = form_data.get(f"michael_{tracking_id}", [""])[0].strip()
            shift_runner_mark = form_data.get(
                f"shift_runner_{tracking_id}", [""]
            )[0].strip()
            weekly_progress = form_data.get(
                f"weekly_progress_{tracking_id}", [""]
            )[0].strip()
            overall_score = form_data.get(f"overall_score_{tracking_id}", [""])[
                0
            ].strip()
            connection.execute(
                """
                UPDATE member_tracking
                SET value_status = ?, conducted_by = ?, michael_mark = ?,
                    shift_runner_mark = ?, weekly_progress = ?, overall_score = ?,
                    updated_at = ?
                WHERE tracking_id = ? AND member_id = ?
                """,
                (
                    value_status,
                    conducted_by,
                    michael_mark,
                    shift_runner_mark,
                    weekly_progress,
                    overall_score,
                    timestamp,
                    tracking_id,
                    member_id,
                ),
            )


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def page(
    title: str,
    body: str,
    message: str = "",
    message_type: str = "success",
    refresh_to: str = "",
    refresh_seconds: int = 1,
) -> bytes:
    message_html = ""
    if message:
        message_html = f'<div class="message {escape(message_type)}">{escape(message)}</div>'
    refresh_html = ""
    if refresh_to:
        refresh_html = (
            f'<meta http-equiv="refresh" content="{escape(refresh_seconds)}; '
            f'url={escape(refresh_to)}">'
        )

    document = f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        {refresh_html}
        <title>{escape(title)}</title>
        <style>
            :root {{
                color-scheme: light;
                --ink: #1f2937;
                --muted: #667085;
                --line: #d7dde7;
                --panel: #ffffff;
                --page: #f5f7fb;
                --primary: #2563eb;
                --primary-dark: #1d4ed8;
                --danger: #b42318;
                --success: #067647;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                min-height: 100vh;
                font-family: Arial, Helvetica, sans-serif;
                color: var(--ink);
                background: var(--page);
            }}

            .shell {{
                width: min(1180px, calc(100% - 32px));
                margin: 0 auto;
                padding: 32px 0 48px;
            }}

            header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-bottom: 24px;
            }}

            h1 {{
                margin: 0;
                font-size: 30px;
                line-height: 1.2;
            }}

            h2 {{
                margin: 32px 0 12px;
                font-size: 22px;
            }}

            p {{
                color: var(--muted);
            }}

            a {{
                color: var(--primary);
                text-decoration: none;
                font-weight: 700;
            }}

            .menu {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 16px;
                margin-top: 24px;
            }}

            .menu a, button, .button {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 44px;
                padding: 10px 16px;
                border: 0;
                border-radius: 6px;
                background: var(--primary);
                color: #ffffff;
                font: inherit;
                font-weight: 700;
                cursor: pointer;
            }}

            .menu a {{
                min-height: 88px;
                font-size: 20px;
            }}

            .button.secondary {{
                color: var(--ink);
                background: #e9edf5;
            }}

            button:hover, .button:hover, .menu a:hover {{
                background: var(--primary-dark);
            }}

            .button.secondary:hover {{
                background: #dbe2ee;
            }}

            .panel {{
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 8px;
                padding: 22px;
            }}

            label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 700;
            }}

            input[type="text"], input[type="number"], textarea {{
                width: 100%;
                border: 1px solid #b8c2d4;
                border-radius: 6px;
                padding: 8px 10px;
                font: inherit;
                background: #ffffff;
            }}

            input[type="text"], input[type="number"] {{
                min-height: 42px;
            }}

            textarea {{
                min-height: 120px;
                resize: vertical;
            }}

            .eye-on-area {{
                margin-bottom: 28px;
            }}

            .eye-on-area label {{
                color: var(--danger);
                font-size: 20px;
            }}

            .eye-on-input {{
                font-weight: 700;
                line-height: 1.4;
            }}

            .form-row {{
                display: grid;
                grid-template-columns: 1fr auto;
                align-items: end;
                gap: 12px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                background: #ffffff;
            }}

            th, td {{
                border: 1px solid var(--line);
                padding: 8px;
                text-align: left;
                vertical-align: middle;
                overflow-wrap: anywhere;
            }}

            th {{
                background: #eef3fb;
                font-weight: 700;
            }}

            td.task {{
                width: 42%;
                font-weight: 700;
            }}

            td.input-cell {{
                width: 29%;
            }}

            .tracker-actions {{
                position: sticky;
                bottom: 0;
                display: flex;
                justify-content: flex-end;
                gap: 10px;
                margin-top: 20px;
                padding: 12px 0 0;
                background: var(--page);
            }}

            .message {{
                margin-bottom: 18px;
                border-radius: 6px;
                padding: 12px 14px;
                font-weight: 700;
                background: #ecfdf3;
                color: var(--success);
                border: 1px solid #abefc6;
            }}

            .message.error {{
                background: #fef3f2;
                color: var(--danger);
                border-color: #fecdca;
            }}

            .empty {{
                border: 1px dashed var(--line);
                border-radius: 8px;
                padding: 24px;
                background: #ffffff;
                color: var(--muted);
                text-align: center;
            }}

            @media (max-width: 720px) {{
                .shell {{
                    width: min(100% - 20px, 1180px);
                    padding-top: 18px;
                }}

                header, .form-row, .menu {{
                    grid-template-columns: 1fr;
                    align-items: stretch;
                }}

                header {{
                    display: grid;
                }}

                table {{
                    min-width: 680px;
                }}

                .table-wrap {{
                    overflow-x: auto;
                }}
            }}
        </style>
    </head>
    <body>
        <main class="shell">
            <header>
                <h1>{escape(title)}</h1>
                <a class="button secondary" href="/">Home</a>
            </header>
            {message_html}
            {body}
        </main>
    </body>
    </html>
    """
    return document.encode("utf-8")


def home_page() -> bytes:
    body = """
    <section class="panel">
        <p>Choose what you want to do.</p>
        <div class="menu">
            <a href="/new">1. New Member Entry</a>
            <a href="/members">2. Existing Team Member</a>
        </div>
    </section>
    """
    return page("Team Member Tracker", body)


def new_member_page(message: str = "", message_type: str = "success") -> bytes:
    body = """
    <section class="panel">
        <form method="post" action="/new">
            <div class="form-row">
                <div>
                    <label for="name">Name</label>
                    <input id="name" name="name" type="text" autocomplete="name" autofocus>
                </div>
                <button type="submit">Save</button>
            </div>
        </form>
    </section>
    """
    return page("New Member Entry", body, message, message_type)


def members_page() -> bytes:
    members = get_members()
    if not members:
        body = """
        <div class="empty">
            No team members saved yet. <a href="/new">Add the first member</a>.
        </div>
        """
        return page("Existing Team Member", body)

    rows = "\n".join(
        f"""
        <tr>
            <td>{escape(member["member_id"])}</td>
            <td>{escape(member["name"])}</td>
            <td><a class="button" href="/tracker/{escape(member["member_id"])}">Open Tracker</a></td>
        </tr>
        """
        for member in members
    )
    body = f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """
    return page("Existing Team Member", body)


def tracker_page(member_id: int, message: str = "") -> bytes:
    member = get_member(member_id)
    if member is None:
        return page(
            "Member Not Found",
            '<div class="empty">This team member does not exist. <a href="/members">View members</a>.</div>',
            "Error: Member was not found.",
            "error",
        )

    tracking = get_tracking(member_id)
    week_sections = []
    for week in WEEKS:
        rows = []
        for task in week["tasks"]:
            record = tracking[(week["name"], task)]
            value_name = f'value_{record["tracking_id"]}'
            conducted_name = f'conducted_{record["tracking_id"]}'
            value_input_type = "number" if task in NUMBER_VALUE_TASKS else "text"
            value_input_step = ' step="any"' if value_input_type == "number" else ""
            value_input_readonly = " readonly" if task == "Weekly Progress" else ""
            rows.append(
                f"""
                <tr>
                    <td class="task">{escape(task)}</td>
                    <td class="input-cell">
                        <input type="{value_input_type}"{value_input_step}{value_input_readonly} name="{escape(value_name)}" value="{escape(record["value_status"])}">
                    </td>
                    <td class="input-cell">
                        <input type="text" name="{escape(conducted_name)}" value="{escape(record["conducted_by"])}">
                    </td>
                </tr>
                """
            )

        week_sections.append(
            f"""
            <h2>{escape(week["name"])}: {escape(week["range"])}</h2>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Task</th>
                            <th>Value / Status</th>
                            <th>Conducted By</th>
                        </tr>
                    </thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            </div>
            """
        )

    body = f"""
    <section class="panel">
        <form method="post" action="/tracker/{escape(member_id)}">
            <div class="eye-on-area">
                <label for="need_to_eye_on">Need to Eye On</label>
                <textarea id="need_to_eye_on" class="eye-on-input" name="need_to_eye_on">{escape(member["need_to_eye_on"])}</textarea>
            </div>
            <p><strong>Team Member:</strong> {escape(member["name"])}</p>
            {''.join(week_sections)}
            <div class="tracker-actions">
                <a class="button secondary" href="/members">Back to Members</a>
                <button type="submit">Save Tracking Data</button>
            </div>
        </form>
    </section>
    """
    return page(f"Weekly Tracker - {member['name']}", body, message)


def redirect(location: str) -> bytes:
    document = f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="1; url={escape(location)}">
        <title>Redirecting</title>
    </head>
    <body>
        <p>Redirecting to <a href="{escape(location)}">{escape(location)}</a>...</p>
    </body>
    </html>
    """
    return document.encode("utf-8")


class TeamTrackerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path == "/":
            self.send_html(home_page())
        elif path == "/new":
            self.send_html(new_member_page())
        elif path == "/members":
            self.send_html(members_page())
        elif path.startswith("/tracker/"):
            member_id = self.member_id_from_path(path)
            if member_id is None:
                self.send_html(page("Error", "<p>Invalid member ID.</p>", "Error: Invalid member ID.", "error"), 400)
            else:
                self.send_html(tracker_page(member_id, query.get("message", [""])[0]))
        else:
            self.send_html(page("Page Not Found", "<p>The requested page does not exist.</p>"), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        form_data = self.read_form()

        if path == "/new":
            saved = add_member(form_data.get("name", [""])[0])
            if saved:
                self.send_html(
                    page(
                        "Name Saved",
                        '<p><a href="/">Return to Home Page</a></p>',
                        "Name has been saved.",
                        refresh_to="/",
                    )
                )
            else:
                self.send_html(
                    new_member_page(
                        "Error: Name was not saved. Please enter a valid name.",
                        "error",
                    ),
                    400,
                )
        elif path.startswith("/tracker/"):
            member_id = self.member_id_from_path(path)
            if member_id is None or get_member(member_id) is None:
                self.send_html(page("Error", "<p>Invalid member ID.</p>", "Error: Invalid member ID.", "error"), 400)
            else:
                save_tracking(member_id, form_data)
                self.send_html(tracker_page(member_id, "Tracking data has been saved."))
        else:
            self.send_html(page("Page Not Found", "<p>The requested page does not exist.</p>"), 404)

    def read_form(self) -> dict[str, list[str]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        return parse_qs(raw_body, keep_blank_values=True)

    def send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def member_id_from_path(path: str) -> int | None:
        try:
            return int(path.rstrip("/").split("/")[-1])
        except ValueError:
            return None

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), TeamTrackerHandler)
    print(f"Team Member Tracker running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()



class handler(TeamTrackerHandler):
    pass
