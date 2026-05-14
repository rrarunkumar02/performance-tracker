from __future__ import annotations

import csv
import hashlib
import hmac
import html
import io
import json
import os
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "team_tracker.db"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_KEY", ""
)
READ_PASSWORD = os.environ.get("READ_PASSWORD", "")
WRITE_PASSWORD = os.environ.get("WRITE_PASSWORD", "")
MASTER_PASSWORD = os.environ.get("MASTER_PASSWORD", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or SUPABASE_KEY or "local-dev-session-secret"
COOKIE_SECURE = os.environ.get(
    "COOKIE_SECURE", "1" if os.environ.get("VERCEL") else "0"
).lower() in {"1", "true", "yes", "on"}
AUTH_COOKIE = "team_tracker_auth"


WEEKS = [
    {
        "name": "Week 0",
        "range": "0-3",
        "tasks": [
            "Bike competency uploaded on Tanda",
            "P2E Level 1",
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
            "Bringing the dough (rotating stock)",
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
            "Delivery time (weekly-mm:ss)",
            "Cut time (2 pizza-ss:ms)",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time (25 pizza-mm:ss)",
            "Cut bench setup time (mm:ss)",
            "Michael Mark",
            "Weekly Progress",
        ],
    },
    {
        "name": "Week 2",
        "range": "6-9",
        "tasks": [
            "Delivery time (weekly-mm:ss)",
            "Cut time (2 pizza-ss:ms)",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time (25 pizza-mm:ss)",
            "Cut bench setup time (mm:ss)",
            "Michael Mark",
            "Weekly Progress",
            "We spent $900 without super. Do we still need to continue with this person?",
        ],
    },
    {
        "name": "Week 3",
        "range": "9-12",
        "tasks": [
            "Delivery time (weekly-mm:ss)",
            "Cut time (2 pizza-ss:ms)",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time (25 pizza-mm:ss)",
            "Cut bench setup time (mm:ss)",
            "Michael Mark",
            "Weekly Progress",
        ],
    },
    {
        "name": "Week 4",
        "range": "12-15",
        "tasks": [
            "Delivery time (weekly-mm:ss)",
            "Cut time (2 pizza-ss:ms)",
            "Cut quiz",
            "Shift runners mark",
            "Counter order test",
            "Saucing time (25 pizza-mm:ss)",
            "Cut bench setup time (mm:ss)",
            "Michael Mark",
            "Weekly Progress",
            "Overall Score",
            "Final $1600 without super. Is this person fit for the store?",
        ],
    },
    {
        "name": "Record Timing Values",
        "range": "",
        "tasks": [
            "Delivery time (weekly-mm:ss)",
            "Cut time (2 pizza-ss:ms)",
            "Cut quiz",
            "Counter order test",
            "Saucing time (25 pizza-mm:ss)",
            "Cut bench setup time (mm:ss)",
            "Total Score",
        ],
    },
]

REPORT_OPTIONS = [
    ("week-1", "Week 1 Report", "Week 1"),
    ("week-2", "Week 2 Report", "Week 2"),
    ("week-3", "Week 3 Report", "Week 3"),
    ("week-4", "Week 4 Report", "Week 4"),
    ("record-timing", "Record Timing Report", "Record Timing Values"),
]
REPORT_WEEK_BY_KEY = {key: week_name for key, _title, week_name in REPORT_OPTIONS}
REPORT_TITLE_BY_KEY = {key: title for key, title, _week_name in REPORT_OPTIONS}


NUMBER_VALUE_TASKS = {
    "Cut quiz",
    "Shift runners mark",
    "Counter order test",
    "Michael Mark",
}

TIME_SCORE_RULES = {
    "Delivery time (weekly-mm:ss)": {"best": "07:00", "worst": "18:00", "format": "minutes_seconds"},
    "Cut time (2 pizza-ss:ms)": {"best": "16:00", "worst": "50:00", "format": "seconds_fraction"},
    "Saucing time (25 pizza-mm:ss)": {"best": "02:30", "worst": "10:00", "format": "minutes_seconds"},
    "Cut bench setup time (mm:ss)": {"best": "07:00", "worst": "18:00", "format": "minutes_seconds"},
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def use_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def auth_enabled() -> bool:
    return bool(MASTER_PASSWORD or READ_PASSWORD or WRITE_PASSWORD)


def sign_session(role: str, name: str) -> str:
    payload = f"{role}:{name}"
    return hmac.new(
        SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def make_auth_cookie(role: str, name: str = "") -> str:
    secure_flag = " Secure;" if COOKIE_SECURE else ""
    safe_name = quote(name, safe="")
    return (
        f"{AUTH_COOKIE}={role}:{safe_name}:{sign_session(role, name)}; Path=/; HttpOnly;"
        f"{secure_flag} SameSite=Lax; Max-Age=2592000"
    )


def clear_auth_cookie() -> str:
    secure_flag = " Secure;" if COOKIE_SECURE else ""
    return f"{AUTH_COOKIE}=; Path=/; HttpOnly;{secure_flag} SameSite=Lax; Max-Age=0"


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies = {}
    for item in cookie_header.split(";"):
        if "=" not in item:
            continue
        key, value = item.strip().split("=", 1)
        cookies[key] = value
    return cookies


def session_from_headers(headers: object) -> dict[str, str]:
    if not auth_enabled():
        return {"role": "write", "name": "Local User"}

    cookie_header = ""
    if hasattr(headers, "get"):
        cookie_header = headers.get("Cookie", "")
    auth_cookie = parse_cookie_header(cookie_header).get(AUTH_COOKIE, "")
    parts = auth_cookie.split(":", 2)
    if len(parts) != 3:
        return {"role": "", "name": ""}

    role, safe_name, signature = parts
    name = unquote(safe_name)
    if role not in {"read", "write", "master"}:
        return {"role": "", "name": ""}
    if not hmac.compare_digest(signature, sign_session(role, name)):
        return {"role": "", "name": ""}
    return {"role": role, "name": name}


def role_from_headers(headers: object) -> str:
    return session_from_headers(headers)["role"]


def user_name_from_headers(headers: object) -> str:
    return session_from_headers(headers)["name"]


def login_identity_from_code(password: str) -> dict[str, str] | None:
    access_user = get_access_user_by_code(password.strip())
    if access_user is not None:
        return {"role": str(access_user["role"]), "name": str(access_user["name"])}
    return None


def master_identity_from_password(password: str) -> dict[str, str] | None:
    clean_password = password.strip()
    if MASTER_PASSWORD and hmac.compare_digest(clean_password, MASTER_PASSWORD):
        return {"role": "master", "name": "Master"}
    return None


def can_read(role: str) -> bool:
    return role in {"read", "write"}


def can_write(role: str) -> bool:
    return role == "write"


def can_manage_access(role: str) -> bool:
    return role == "master"


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
    try:
        with urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        print(f"Supabase {method} {table} failed: {error.code} {details}")
        raise RuntimeError(
            f"Supabase {method} {table} failed: {error.code} {details}"
        ) from error
    except URLError as error:
        print(f"Supabase {method} {table} connection failed: {error}")
        raise RuntimeError(
            f"Supabase {method} {table} connection failed: {error}"
        ) from error
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
            CREATE TABLE IF NOT EXISTS access_users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                access_code TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'write',
                created_at TEXT NOT NULL
            )
            """
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
        task_renames = [
            ("Week 0", "Bike competency", "Bike competency uploaded on Tanda"),
            ("Week 0", "P2E Level 2", "P2E Level 1"),
            ("Week 0", "Bringing the dough", "Bringing the dough (rotating stock)"),
            ("Week 1", "Delivery time", "Delivery time (weekly-mm:ss)"),
            ("Week 1", "Cut time", "Cut time (2 pizza-ss:ms)"),
            ("Week 1", "Saucing time", "Saucing time (25 pizza-mm:ss)"),
            ("Week 2", "Delivery time", "Delivery time (weekly-mm:ss)"),
            ("Week 2", "Cut time", "Cut time (2 pizza-ss:ms)"),
            ("Week 2", "Saucing time", "Saucing time (25 pizza-mm:ss)"),
            ("Week 3", "Delivery time", "Delivery time (weekly-mm:ss)"),
            ("Week 3", "Cut time", "Cut time (2 pizza-ss:ms)"),
            ("Week 3", "Saucing time", "Saucing time (25 pizza-mm:ss)"),
            ("Week 4", "Delivery time", "Delivery time (weekly-mm:ss)"),
            ("Week 4", "Cut time", "Cut time (2 pizza-ss:ms)"),
            ("Week 4", "Saucing time", "Saucing time (25 pizza-mm:ss)"),
            ("Record Timing Values", "Delivery time", "Delivery time (weekly-mm:ss)"),
            ("Record Timing Values", "Cut time", "Cut time (2 pizza-ss:ms)"),
            ("Record Timing Values", "Saucing time", "Saucing time (25 pizza-mm:ss)"),
            ("Week 1", "Cut bench setup time", "Cut bench setup time (mm:ss)"),
            ("Week 2", "Cut bench setup time", "Cut bench setup time (mm:ss)"),
            ("Week 3", "Cut bench setup time", "Cut bench setup time (mm:ss)"),
            ("Week 4", "Cut bench setup time", "Cut bench setup time (mm:ss)"),
            ("Record Timing Values", "Cut bench setup time", "Cut bench setup time (mm:ss)"),
        ]
        for week_name, old_task, new_task in task_renames:
            connection.execute(
                """
                UPDATE member_tracking
                SET task_name = ?
                WHERE week_name = ?
                  AND task_name = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM member_tracking AS existing
                      WHERE existing.member_id = member_tracking.member_id
                        AND existing.week_name = member_tracking.week_name
                        AND existing.task_name = ?
                  )
                """,
                (new_task, week_name, old_task, new_task),
            )


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def display_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(" ", 1)[0]


def normalize_role(role: str) -> str:
    return "read" if role == "read" else "write"


def delete_access_user(user_id: int) -> None:
    if use_supabase():
        query = urlencode({"user_id": f"eq.{user_id}"})
        supabase_request("DELETE", "access_users", query, prefer="return=minimal")
        return

    with get_connection() as connection:
        connection.execute("DELETE FROM access_users WHERE user_id = ?", (user_id,))


def delete_member(member_id: int) -> None:
    if use_supabase():
        tracking_query = urlencode({"member_id": f"eq.{member_id}"})
        supabase_request("DELETE", "member_tracking", tracking_query, prefer="return=minimal")
        member_query = urlencode({"member_id": f"eq.{member_id}"})
        supabase_request("DELETE", "members", member_query, prefer="return=minimal")
        return

    with get_connection() as connection:
        connection.execute("DELETE FROM member_tracking WHERE member_id = ?", (member_id,))
        connection.execute("DELETE FROM members WHERE member_id = ?", (member_id,))


def add_access_user(name: str, access_code: str, role: str) -> bool:
    clean_name = name.strip()
    clean_code = access_code.strip()
    clean_role = normalize_role(role.strip())
    if not clean_name or not clean_code:
        return False

    if get_access_user_by_code(clean_code) is not None:
        return False

    if use_supabase():
        supabase_request(
            "POST",
            "access_users",
            payload={
                "name": clean_name,
                "access_code": clean_code,
                "role": clean_role,
                "created_at": now_text(),
            },
            prefer="return=minimal",
        )
        return True

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO access_users (name, access_code, role, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (clean_name, clean_code, clean_role, now_text()),
        )
    return True


def get_access_users() -> list[sqlite3.Row]:
    if use_supabase():
        query = urlencode(
            {
                "select": "user_id,name,role,created_at",
                "order": "name.asc",
            }
        )
        return supabase_request("GET", "access_users", query)

    with get_connection() as connection:
        return list(
            connection.execute(
                """
                SELECT user_id, name, role, created_at
                FROM access_users
                ORDER BY name
                """
            )
        )


def get_access_user_by_code(access_code: str) -> sqlite3.Row | dict[str, object] | None:
    clean_code = access_code.strip()
    if not clean_code:
        return None

    if use_supabase():
        query = urlencode(
            {
                "select": "user_id,name,role,created_at",
                "access_code": f"eq.{clean_code}",
                "limit": "1",
            }
        )
        rows = supabase_request("GET", "access_users", query)
        return rows[0] if rows else None

    with get_connection() as connection:
        return connection.execute(
            """
            SELECT user_id, name, role, created_at
            FROM access_users
            WHERE access_code = ?
            """,
            (clean_code,),
        ).fetchone()


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
                        "value_status": "",
                        "conducted_by": "",
                        "updated_at": timestamp,
                    }
                )
        query = urlencode({"on_conflict": "member_id,week_name,task_name"})
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
                    "value_status,conducted_by,updated_at"
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


def clean_number_value(value: str) -> str:
    number_value = parse_float(value)
    if number_value is None:
        return ""
    number_value = max(0, min(100, number_value))
    return f"{number_value:.2f}".rstrip("0").rstrip(".")


def parse_minutes_seconds(value: str) -> float | None:
    clean_value = value.strip()
    if not clean_value or ":" not in clean_value:
        return None
    minutes_text, seconds_text = clean_value.split(":", 1)
    if not minutes_text.isdigit() or not seconds_text.isdigit():
        return None
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    if seconds >= 60:
        return None
    return float(minutes * 60 + seconds)


def parse_seconds_fraction(value: str) -> float | None:
    clean_value = value.strip()
    if not clean_value or ":" not in clean_value:
        return None
    seconds_text, fraction_text = clean_value.split(":", 1)
    if not seconds_text.isdigit() or not fraction_text.isdigit():
        return None
    seconds = int(seconds_text)
    fraction = int(fraction_text) / (10 ** len(fraction_text))
    return seconds + fraction


def parse_task_time_value(task: str, value: str) -> float | None:
    rule = TIME_SCORE_RULES.get(task)
    if rule is None:
        return None
    if rule["format"] == "seconds_fraction":
        return parse_seconds_fraction(value)
    return parse_minutes_seconds(value)


def clean_time_value(task: str, value: str) -> str:
    clean_value = value.strip()
    if task not in TIME_SCORE_RULES:
        return clean_value
    if TIME_SCORE_RULES[task]["format"] == "seconds_fraction":
        seconds_value = parse_seconds_fraction(clean_value)
        if seconds_value is None:
            return ""
        whole_seconds = int(seconds_value)
        fraction_text = clean_value.split(":", 1)[1]
        return f"{whole_seconds:02d}:{fraction_text}"

    seconds_total = parse_minutes_seconds(clean_value)
    if seconds_total is None:
        return ""
    minutes, seconds = divmod(int(seconds_total), 60)
    return f"{minutes:02d}:{seconds:02d}"


def task_score_value(task: str, value: str) -> float | None:
    if task in TIME_SCORE_RULES:
        actual_value = parse_task_time_value(task, value)
        best_value = parse_task_time_value(task, TIME_SCORE_RULES[task]["best"])
        worst_value = parse_task_time_value(task, TIME_SCORE_RULES[task]["worst"])
        if actual_value is None or best_value is None or worst_value is None:
            return None
        if best_value == worst_value:
            return 100.0 if actual_value <= best_value else 0.0
        score = (worst_value - actual_value) / (worst_value - best_value) * 100
        return max(0.0, min(100.0, score))
    if task in NUMBER_VALUE_TASKS:
        return parse_float(value)
    return None


def format_average(values: list[float]) -> str:
    if not values:
        return ""
    average = sum(values) / len(values)
    return f"{average:.2f}".rstrip("0").rstrip(".")


def calculate_weekly_progress(
    form_data: dict[str, list[str]], tracking: dict[tuple[str, str], sqlite3.Row]
) -> dict[int, str]:
    calculated_values = {}
    weekly_progress_by_week = {}
    overall_score_id = None

    for week in WEEKS:
        marks = []
        score_target_id = None
        for task in week["tasks"]:
            record = tracking.get((week["name"], task))
            if record is None:
                continue

            tracking_id = int(record["tracking_id"])
            if task in {"Weekly Progress", "Total Score"}:
                score_target_id = tracking_id
                continue
            if task == "Overall Score":
                overall_score_id = tracking_id
                continue

            form_value = form_data.get(
                f"value_{tracking_id}", [str(record["value_status"] or "")]
            )[0]
            score_value = task_score_value(task, form_value)
            if score_value is not None:
                marks.append(score_value)

        if score_target_id is not None:
            score_value = format_average(marks)
            calculated_values[score_target_id] = score_value
            if week["name"] in {"Week 1", "Week 2", "Week 3", "Week 4"}:
                weekly_progress_by_week[week["name"]] = score_value

    if overall_score_id is not None:
        progress_scores = []
        for week_name in ["Week 1", "Week 2", "Week 3", "Week 4"]:
            value = weekly_progress_by_week.get(week_name, "")
            number_value = parse_float(value)
            if number_value is not None:
                progress_scores.append(number_value)
        calculated_values[overall_score_id] = format_average(progress_scores)

    return calculated_values


def save_tracking(member_id: int, form_data: dict[str, list[str]], conducted_by_name: str = "") -> None:
    timestamp = now_text()
    need_to_eye_on = form_data.get("need_to_eye_on", [""])[0].strip()
    tracking = get_tracking(member_id)
    weekly_progress_values = calculate_weekly_progress(form_data, tracking)
    records_by_id = {int(record["tracking_id"]): record for record in tracking.values()}
    for tracking_id, record in records_by_id.items():
        if str(record["week_name"] or "") == "Week 0" and f"value_{tracking_id}" not in form_data:
            form_data[f"value_{tracking_id}"] = [""]
    logged_in_name = conducted_by_name.strip()
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
            record = records_by_id.get(tracking_id)
            task_name = str(record["task_name"] or "") if record else ""
            if task_name in TIME_SCORE_RULES:
                value_status = clean_time_value(task_name, value_status)
            elif task_name in NUMBER_VALUE_TASKS:
                value_status = clean_number_value(value_status)
            if tracking_id in weekly_progress_values:
                value_status = weekly_progress_values[tracking_id]
            previous_value = str(record["value_status"] or "").strip() if record else ""
            previous_conducted_by = str(record["conducted_by"] or "").strip() if record else ""
            row_changed = value_status != previous_value
            if not row_changed:
                continue
            if not value_status:
                conducted_by = ""
            elif logged_in_name and task_name not in {"Weekly Progress", "Total Score", "Overall Score"}:
                conducted_by = logged_in_name
            else:
                conducted_by = previous_conducted_by
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
            record = records_by_id.get(tracking_id)
            task_name = str(record["task_name"] or "") if record else ""
            if task_name in TIME_SCORE_RULES:
                value_status = clean_time_value(task_name, value_status)
            elif task_name in NUMBER_VALUE_TASKS:
                value_status = clean_number_value(value_status)
            if tracking_id in weekly_progress_values:
                value_status = weekly_progress_values[tracking_id]
            previous_value = str(record["value_status"] or "").strip() if record else ""
            previous_conducted_by = str(record["conducted_by"] or "").strip() if record else ""
            row_changed = value_status != previous_value
            if not row_changed:
                continue
            if not value_status:
                conducted_by = ""
            elif logged_in_name and task_name not in {"Weekly Progress", "Total Score", "Overall Score"}:
                conducted_by = logged_in_name
            else:
                conducted_by = previous_conducted_by
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


def task_label_html(task: str) -> str:
    if task == "Bringing the dough (rotating stock)":
        return 'Bringing the dough <span class="task-note">(rotating stock)</span>'
    return escape(task)


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

            .button.danger {{
                color: #ffffff;
                background: var(--danger);
            }}

            input:disabled, textarea:disabled {{
                color: var(--ink);
                background: #f3f4f6;
                cursor: not-allowed;
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

            input[type="text"], input[type="number"], input[type="password"], select, textarea {{
                width: 100%;
                border: 1px solid #b8c2d4;
                border-radius: 6px;
                padding: 8px 10px;
                font: inherit;
                background: #ffffff;
            }}

            input[type="text"], input[type="number"], input[type="password"], select {{
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

            .checkbox-cell {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                margin: 0;
                font-weight: 700;
            }}

            .checkbox-cell input {{
                width: 18px;
                height: 18px;
            }}

            .member-picker {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 10px;
                margin-top: 12px;
            }}

            .date-note {{
                display: inline-block;
                margin-top: 4px;
                color: var(--muted);
                font-size: 13px;
                font-weight: 700;
            }}

            .task-note {{
                display: block;
                margin-top: 3px;
                color: var(--muted);
                font-size: 12px;
                font-weight: 700;
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


def master_login_page(message: str = "", message_type: str = "error") -> bytes:
    body = """
    <section class="panel">
        <form method="post" action="/master">
            <div class="form-row">
                <div>
                    <label for="password">Master Password</label>
                    <input id="password" name="password" type="password" autofocus>
                </div>
                <button type="submit">Open Access Setup</button>
            </div>
        </form>
    </section>
    """
    return page("Master Access", body, message, message_type)


def login_page(message: str = "", message_type: str = "error") -> bytes:
    body = """
    <section class="panel">
        <form method="post" action="/login">
            <div class="form-row">
                <div>
                    <label for="password">Access Code</label>
                    <input id="password" name="password" type="password" autofocus>
                </div>
                <button type="submit">Log In</button>
            </div>
        </form>
    </section>
    """
    return page("Team Member Tracker Login", body, message, message_type)


def home_page(can_write_access: bool = True) -> bytes:
    new_member_link = (
        '<a href="/new">1. New Member Entry</a>'
        if can_write_access
        else '<span class="button secondary">1. New Member Entry</span>'
    )
    readonly_message = "" if can_write_access else '<div class="message">Read-only access. You can view this tracker, but cannot save changes.</div>'
    body = f"""
    <section class="panel">
        {readonly_message}
        <p>Choose what you want to do.</p>
        <div class="menu">
            {new_member_link}
            <a href="/members">2. Existing Team Member</a>
            <a href="/report">3. Report</a>
            <a href="/logout">4. Logout</a>
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


def access_page(message: str = "", message_type: str = "success") -> bytes:
    users = get_access_users()
    members = get_members()
    user_rows = "".join(
        f"""
        <tr>
            <td>{escape(user["name"])}</td>
            <td>{escape(user["role"]).title()}</td>
            <td>{escape(user["created_at"])}</td>
            <td>
                <form method="post" action="/access">
                    <input type="hidden" name="action" value="delete_access_user">
                    <input type="hidden" name="user_id" value="{escape(user["user_id"])}">
                    <button class="button danger" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """
        for user in users
    ) or '<tr><td colspan="4">No access codes saved yet.</td></tr>'
    member_rows = "".join(
        f"""
        <tr>
            <td>{escape(member["member_id"])}</td>
            <td>{escape(member["name"])}</td>
            <td>{escape(member["created_at"])}</td>
            <td>
                <form method="post" action="/access">
                    <input type="hidden" name="action" value="delete_member">
                    <input type="hidden" name="member_id" value="{escape(member["member_id"])}">
                    <button class="button danger" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        """
        for member in members
    ) or '<tr><td colspan="4">No team members saved yet.</td></tr>'
    body = f"""
    <section class="panel">
        <form method="post" action="/access">
            <input type="hidden" name="action" value="add_access_user">
            <div class="form-row">
                <div>
                    <label for="name">Name</label>
                    <input id="name" name="name" type="text" autocomplete="name" autofocus>
                </div>
                <div>
                    <label for="access_code">Access Code</label>
                    <input id="access_code" name="access_code" type="text" autocomplete="off">
                </div>
                <div>
                    <label for="role">Access</label>
                    <select id="role" name="role">
                        <option value="write">Write</option>
                        <option value="read">Read Only</option>
                    </select>
                </div>
                <button type="submit">Save Access</button>
            </div>
        </form>
    </section>
    <section class="panel" style="margin-top: 18px;">
        <h2>People With Access</h2>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Access</th>
                        <th>Created</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>{user_rows}</tbody>
            </table>
        </div>
    </section>
    <section class="panel" style="margin-top: 18px;">
        <h2>Existing Team Members</h2>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Created</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>{member_rows}</tbody>
            </table>
        </div>
    </section>
    """
    return page("Access Codes", body, message, message_type)

REPORT_SCORE_SKIP_TASKS = {"Weekly Progress", "Overall Score", "Total Score"}


def report_total_score(values_by_task: dict[str, str]) -> str:
    marks = []
    for task, value in values_by_task.items():
        if task in REPORT_SCORE_SKIP_TASKS:
            continue
        score_value = task_score_value(task, value)
        if score_value is not None:
            marks.append(score_value)
    return format_average(marks)


def report_rows_for(
    report_key: str, selected_member_ids: list[int] | None = None, sort_dir: str = "asc"
) -> tuple[list[str], list[tuple[sqlite3.Row, dict[str, str], str]]]:
    week_name = REPORT_WEEK_BY_KEY.get(report_key)
    if week_name is None:
        return [], []

    week = next((item for item in WEEKS if item["name"] == week_name), None)
    tasks = week["tasks"] if week else []
    selected_ids = set(selected_member_ids or [])
    members = [member for member in get_members() if int(member["member_id"]) in selected_ids]

    rows = []
    for member in members:
        tracking = get_tracking(int(member["member_id"]))
        values_by_task = {}
        for task in tasks:
            record = tracking.get((week_name, task))
            values_by_task[task] = str(record["value_status"] or "").strip() if record else ""
        rows.append((member, values_by_task, report_total_score(values_by_task)))

    sort_desc = sort_dir == "desc"

    def score_key(item: tuple[sqlite3.Row, dict[str, str], str]) -> tuple[bool, float, str]:
        member, _values_by_task, total_score = item
        number = parse_float(total_score)
        if number is None:
            return (True, 0, str(member["name"] or "").lower())
        score = -number if sort_desc else number
        return (False, score, str(member["name"] or "").lower())

    rows.sort(key=score_key)
    return tasks, rows


def report_csv(
    report_key: str, selected_member_ids: list[int] | None = None, sort_dir: str = "asc"
) -> tuple[str, bytes]:
    tasks, rows = report_rows_for(report_key, selected_member_ids, sort_dir)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Team Member", *tasks, "Total Score"])
    for member, values_by_task, total_score in rows:
        writer.writerow(
            [str(member["name"] or ""), *[values_by_task.get(task, "") for task in tasks], total_score]
        )
    filename = f"{report_key or 'report'}.csv"
    return filename, output.getvalue().encode("utf-8")


def report_page(
    report_key: str = "",
    selected_member_ids: list[int] | None = None,
    sort_dir: str = "asc",
) -> bytes:
    if not report_key:
        cards = "".join(
            f'<a href="/report/{escape(key)}">{escape(title)}</a>'
            for key, title, _week_name in REPORT_OPTIONS
        )
        body = f"""
        <section class="panel">
            <p>Select the report you want to view.</p>
            <div class="menu">{cards}</div>
        </section>
        """
        return page("Reports", body)

    week_name = REPORT_WEEK_BY_KEY.get(report_key)
    if week_name is None:
        return page("Report Not Found", '<div class="empty">This report does not exist.</div>', "Error: Report was not found.", "error")

    members = get_members()
    selected_ids = set(selected_member_ids or [])
    member_options = "".join(
        f"""
        <label class="checkbox-cell">
            <input type="checkbox" name="member_id" value="{escape(member["member_id"])}"{' checked' if int(member["member_id"]) in selected_ids else ''}>
            {escape(member["name"])}
        </label>
        """
        for member in members
    ) or '<p>No team members saved yet.</p>'

    selected_members = [member for member in members if int(member["member_id"]) in selected_ids]
    week = next((item for item in WEEKS if item["name"] == week_name), None)
    tasks = week["tasks"] if week else []
    sort_dir = "desc" if sort_dir == "desc" else "asc"
    asc_selected = " selected" if sort_dir == "asc" else ""
    desc_selected = " selected" if sort_dir == "desc" else ""
    direction_options = (
        f'<option value="asc"{asc_selected}>Ascending</option>'
        f'<option value="desc"{desc_selected}>Descending</option>'
    )

    comparison_table = '<div class="empty">Select team members, then click View Report.</div>'
    export_link = ""
    if selected_members:
        _tasks, report_rows = report_rows_for(report_key, selected_member_ids, sort_dir)
        header_cells = "".join(f"<th>{escape(task)}</th>" for task in tasks)
        rows = []
        for member, values_by_task, total_score in report_rows:
            cells = [f"<td>{escape(values_by_task.get(task, ''))}</td>" for task in tasks]
            rows.append(
                f"""
                <tr>
                    <td class="task">{escape(member["name"])}</td>
                    {''.join(cells)}
                    <td>{escape(total_score)}</td>
                </tr>
                """
            )
        selected_query = "".join(
            f"&member_id={escape(member_id)}" for member_id in selected_member_ids or []
        )
        export_href = f"/report/{escape(report_key)}/export?sort_dir={escape(sort_dir)}{selected_query}"
        export_link = (
            f'<a class="button secondary" href="{export_href}" download="{escape(report_key)}.csv">Export CSV</a>'
            f'<a class="button secondary" href="{export_href}&view=1" target="_blank">Open CSV</a>'
        )
        comparison_table = f"""
        <p>Sorted by Total Score.</p>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Team Member</th>
                        {header_cells}
                        <th>Total Score</th>
                    </tr>
                </thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </div>
        """

    body = f"""
    <section class="panel">
        <form method="get" action="/report/{escape(report_key)}">
            <h2>Select Team Members</h2>
            <div class="member-picker">{member_options}</div>
            <div class="form-row" style="margin-top: 16px;">
                <div>
                    <label for="sort_dir">Order by Total Score</label>
                    <select id="sort_dir" name="sort_dir">{direction_options}</select>
                </div>
                <button type="submit">View Report</button>
            </div>
            <div class="tracker-actions">
                <a class="button secondary" href="/report">Back to Reports</a>
            </div>
        </form>
    </section>
    <section class="panel" style="margin-top: 18px;">
        <h2>{escape(REPORT_TITLE_BY_KEY[report_key])}</h2>
        <div class="tracker-actions">{export_link}</div>
        {comparison_table}
    </section>
    """
    return page(REPORT_TITLE_BY_KEY[report_key], body)

def tracker_page(member_id: int, message: str = "", can_write_access: bool = True) -> bytes:
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
            disabled = " disabled" if not can_write_access else ""
            if week["name"] == "Week 0":
                checked = " checked" if str(record["value_status"] or "").strip() == "Done" else ""
                value_control = (
                    f'<label class="checkbox-cell">'
                    f'<input type="checkbox" name="{escape(value_name)}" value="Done"{checked}{disabled}> Done'
                    f'</label>'
                )
            else:
                value_input_type = "number" if task in NUMBER_VALUE_TASKS else "text"
                value_input_step = ' step="any" min="0" max="100"' if value_input_type == "number" else ""
                value_input_readonly = " readonly" if task in {"Weekly Progress", "Total Score", "Overall Score"} else ""
                if task in TIME_SCORE_RULES:
                    placeholder_text = "ss:ms" if TIME_SCORE_RULES[task]["format"] == "seconds_fraction" else "mm:ss"
                    value_input_placeholder = f' placeholder="{placeholder_text}"'
                else:
                    value_input_placeholder = ""
                value_control = (
                    f'<input type="{value_input_type}"{value_input_step}{value_input_readonly}{value_input_placeholder}{disabled} '
                    f'name="{escape(value_name)}" value="{escape(record["value_status"])}">'
                )
            value_display = str(record["value_status"] or "").strip()
            conducted_display = str(record["conducted_by"] or "").strip()
            date_display = display_date(record["updated_at"])
            conducted_detail = ""
            if value_display and conducted_display:
                conducted_detail = conducted_display
                if date_display:
                    conducted_detail = f'{conducted_display}<br><span class="date-note">{escape(date_display)}</span>'
            rows.append(
                f"""
                <tr>
                    <td class="task">{task_label_html(task)}</td>
                    <td class="input-cell">{value_control}</td>
                    <td class="input-cell conducted-cell">{conducted_detail}</td>
                </tr>
                """
            )

        week_heading_map = {
            "Week 0": "Week-1 (0-9 hours, 3 shift)",
            "Week 1": "Week-2 (9-18 hours, 6 shift)",
            "Week 2": "Week-3 (18-27 hours, 9 shift)",
            "Week 3": "Week-4 (27-36 hours, 12 shift)",
            "Week 4": "Week-5 (36-45 hours, 15 shift)",
        }
        week_heading = week_heading_map.get(week["name"], week["name"])
        week_sections.append(
            f"""
            <h2>{escape(week_heading)}</h2>
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

    readonly_message = "" if can_write_access else '<div class="message">Read-only access. You can view this tracker, but cannot save changes.</div>'
    save_button = '<button type="submit">Save Tracking Data</button>' if can_write_access else ""
    textarea_disabled = "" if can_write_access else " disabled"
    body = f"""
    <section class="panel">
        {readonly_message}
        <form method="post" action="/tracker/{escape(member_id)}">
            <div class="eye-on-area">
                <label for="need_to_eye_on">Internal Review Notes</label>
                <textarea id="need_to_eye_on" class="eye-on-input" name="need_to_eye_on"{textarea_disabled}>{escape(member["need_to_eye_on"])}</textarea>
            </div>
            <p><strong>Team Member:</strong> {escape(member["name"])}</p>
            {''.join(week_sections)}
            <div class="tracker-actions">
                <a class="button secondary" href="/members">Back to Members</a>
                {save_button}
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

        if path == "/login":
            self.send_html(login_page())
            return
        if path == "/master":
            self.send_html(master_login_page())
            return
        if path == "/logout":
            self.send_html(
                page("Logged Out", '<p><a href="/login">Log in again</a>.</p>', "You have been logged out.", refresh_to="/login"),
                headers=[("Set-Cookie", clear_auth_cookie())],
            )
            return

        role = role_from_headers(self.headers)
        if path == "/access":
            if not can_manage_access(role):
                self.send_html(master_login_page("Please enter the master password to manage access codes."), 401)
            else:
                self.send_html(access_page())
            return

        if not can_read(role):
            self.send_html(login_page("Please log in to continue."), 401)
            return

        if path == "/":
            self.send_html(home_page(can_write(role)))
        elif path == "/new":
            if not can_write(role):
                self.send_html(page("Access Denied", "<p>You have read-only access.</p>", "Write access is required.", "error"), 403)
            else:
                self.send_html(new_member_page())
        elif path == "/members":
            self.send_html(members_page())
        elif path == "/report":
            self.send_html(report_page())
        elif path.startswith("/report/"):
            path_parts = path.strip("/").split("/")
            is_export = len(path_parts) == 3 and path_parts[0] == "report" and path_parts[2] == "export"
            report_key = path_parts[1] if is_export else path.rstrip("/").split("/")[-1]
            selected_ids = []
            for value in query.get("member_id", []):
                try:
                    selected_ids.append(int(value))
                except ValueError:
                    pass
            sort_dir = query.get("sort_dir", ["asc"])[0]
            if is_export:
                filename, body = report_csv(report_key, selected_ids, sort_dir)
                if query.get("view", [""])[0] == "1":
                    self.send_bytes(body, "text/plain; charset=utf-8")
                else:
                    self.send_bytes(
                        body,
                        "text/csv; charset=utf-8",
                        headers=[
                            ("Content-Disposition", f'attachment; filename="{filename}"'),
                            ("Cache-Control", "no-store"),
                        ],
                    )
            else:
                self.send_html(report_page(report_key, selected_ids, sort_dir))
        elif path.startswith("/tracker/"):
            member_id = self.member_id_from_path(path)
            if member_id is None:
                self.send_html(page("Error", "<p>Invalid member ID.</p>", "Error: Invalid member ID.", "error"), 400)
            else:
                self.send_html(tracker_page(member_id, query.get("message", [""])[0], can_write(role)))
        else:
            self.send_html(page("Page Not Found", "<p>The requested page does not exist.</p>"), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        form_data = self.read_form()

        if path == "/login":
            identity = login_identity_from_code(form_data.get("password", [""])[0])
            if identity:
                self.send_html(
                    page("Logged In", '<p><a href="/">Continue to tracker</a>.</p>', "Login successful.", refresh_to="/"),
                    headers=[("Set-Cookie", make_auth_cookie(identity["role"], identity["name"]))],
                )
            else:
                self.send_html(login_page("Invalid access code. Please try again."), 401)
            return
        if path == "/master":
            identity = master_identity_from_password(form_data.get("password", [""])[0])
            if identity:
                self.send_html(
                    page("Master Login", '<p><a href="/access">Continue to access setup</a>.</p>', "Master login successful.", refresh_to="/access"),
                    headers=[("Set-Cookie", make_auth_cookie(identity["role"], identity["name"]))],
                )
            else:
                self.send_html(master_login_page("Invalid master password. Please try again."), 401)
            return

        role = role_from_headers(self.headers)
        if path == "/access":
            if not can_manage_access(role):
                self.send_html(master_login_page("Please enter the master password to manage access codes."), 401)
                return
            action = form_data.get("action", ["add_access_user"])[0]
            if action == "delete_access_user":
                try:
                    delete_access_user(int(form_data.get("user_id", ["0"])[0]))
                    self.send_html(access_page("Access person has been deleted."))
                except ValueError:
                    self.send_html(access_page("Error: Access person was not deleted.", "error"), 400)
                return
            if action == "delete_member":
                try:
                    delete_member(int(form_data.get("member_id", ["0"])[0]))
                    self.send_html(access_page("Team member has been deleted."))
                except ValueError:
                    self.send_html(access_page("Error: Team member was not deleted.", "error"), 400)
                return

            saved = add_access_user(
                form_data.get("name", [""])[0],
                form_data.get("access_code", [""])[0],
                form_data.get("role", ["write"])[0],
            )
            if saved:
                self.send_html(access_page("Access code has been saved."))
            else:
                self.send_html(
                    access_page("Error: This access code is already being used, or the name/code is empty.", "error"),
                    400,
                )
            return

        if not can_write(role):
            self.send_html(page("Access Denied", "<p>You have read-only access.</p>", "Write access is required.", "error"), 403)
            return

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
                save_tracking(member_id, form_data, user_name_from_headers(self.headers))
                self.send_html(tracker_page(member_id, "Tracking data has been saved.", True))
        else:
            self.send_html(page("Page Not Found", "<p>The requested page does not exist.</p>"), 404)

    def read_form(self) -> dict[str, list[str]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        return parse_qs(raw_body, keep_blank_values=True)

    def send_html(
        self, body: bytes, status: int = 200, headers: list[tuple[str, str]] | None = None
    ) -> None:
        self.send_bytes(body, "text/html; charset=utf-8", status, headers)

    def send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: int = 200,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in headers or []:
            self.send_header(key, value)
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
