from __future__ import annotations

from pathlib import Path
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import (
    add_member,
    can_read,
    can_write,
    clear_auth_cookie,
    get_member,
    home_page,
    login_page,
    make_auth_cookie,
    members_page,
    new_member_page,
    page,
    role_from_headers,
    role_from_password,
    save_tracking,
    tracker_page,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path == "/login":
            self.send_html(login_page())
            return
        if path == "/logout":
            self.send_html(
                page("Logged Out", '<p><a href="/login">Log in again</a>.</p>', "You have been logged out.", refresh_to="/login"),
                headers=[("Set-Cookie", clear_auth_cookie())],
            )
            return

        role = role_from_headers(self.headers)
        if not can_read(role):
            self.send_html(login_page("Please log in to continue."), 401)
            return

        if path in {"/", "/api/index.py"}:
            self.send_html(home_page(can_write(role)))
        elif path == "/new":
            if not can_write(role):
                self.send_html(page("Access Denied", "<p>You have read-only access.</p>", "Write access is required.", "error"), 403)
            else:
                self.send_html(new_member_page())
        elif path == "/members":
            self.send_html(members_page())
        elif path.startswith("/tracker/"):
            member_id = self.member_id_from_path(path)
            if member_id is None:
                self.send_html(
                    page("Error", "<p>Invalid member ID.</p>", "Error: Invalid member ID.", "error"),
                    400,
                )
            else:
                self.send_html(tracker_page(member_id, query.get("message", [""])[0], can_write(role)))
        else:
            self.send_html(page("Page Not Found", "<p>The requested page does not exist.</p>"), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        form_data = self.read_form()

        if path == "/login":
            role = role_from_password(form_data.get("password", [""])[0])
            if role:
                self.send_html(
                    page("Logged In", '<p><a href="/">Continue to tracker</a>.</p>', "Login successful.", refresh_to="/"),
                    headers=[("Set-Cookie", make_auth_cookie(role))],
                )
            else:
                self.send_html(login_page("Invalid password. Please try again."), 401)
            return

        role = role_from_headers(self.headers)
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
                self.send_html(
                    page("Error", "<p>Invalid member ID.</p>", "Error: Invalid member ID.", "error"),
                    400,
                )
            else:
                save_tracking(member_id, form_data)
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
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
