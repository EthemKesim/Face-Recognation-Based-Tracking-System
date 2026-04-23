from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from .data_access import (
        PROJECT_SOURCE_DIR,
        build_employee_rows,
        filter_events,
        filter_records,
        get_dashboard_data,
        get_employee_detail,
        get_status_rules,
        json_bytes,
    )
except ImportError:
    from data_access import (
        PROJECT_SOURCE_DIR,
        build_employee_rows,
        filter_events,
        filter_records,
        get_dashboard_data,
        get_employee_detail,
        get_status_rules,
        json_bytes,
    )

if str(PROJECT_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE_DIR))

from database_utils import delete_employee_record


HOST = "127.0.0.1"
PORT = 8000
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
ENV_PATH = PROJECT_SOURCE_DIR / ".env"
SESSION_COOKIE_NAME = "dashboard_session"
SESSION_DURATION_SECONDS = 60 * 60 * 8
PUBLIC_FRONTEND_FILES = {"styles.css"}


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)


def get_auth_settings() -> dict[str, str]:
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    session_secret = os.environ.get("SESSION_SECRET", "").strip()

    missing = [
        key
        for key, value in {
            "ADMIN_USERNAME": username,
            "ADMIN_PASSWORD": password,
            "SESSION_SECRET": session_secret,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required auth environment variables in {ENV_PATH}: {', '.join(missing)}"
        )

    return {
        "username": username,
        "password": password,
        "session_secret": session_secret,
    }


def encode_session_token(username: str) -> str:
    auth_settings = get_auth_settings()
    expires_at = int(time.time()) + SESSION_DURATION_SECONDS
    payload = json.dumps({"username": username, "expires_at": expires_at}, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(
        auth_settings["session_secret"].encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{token}.{signature}"


def decode_session_token(token_value: str) -> dict[str, str] | None:
    if not token_value or "." not in token_value:
        return None

    token, signature = token_value.rsplit(".", 1)
    expected_signature = hmac.new(
        get_auth_settings()["session_secret"].encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return None

    padding = "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(f"{token}{padding}").decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("expires_at", 0) < int(time.time()):
        return None

    username = payload.get("username")
    if not isinstance(username, str) or not username:
        return None

    return {"username": username}


def build_session_cookie(username: str) -> str:
    return (
        f"{SESSION_COOKIE_NAME}={encode_session_token(username)}; "
        f"HttpOnly; Max-Age={SESSION_DURATION_SECONDS}; Path=/; SameSite=Lax"
    )


def clear_session_cookie() -> str:
    return (
        f"{SESSION_COOKIE_NAME}=; HttpOnly; Expires=Thu, 01 Jan 1970 00:00:00 GMT; "
        "Max-Age=0; Path=/; SameSite=Lax"
    )


def extract_employee_id(path: str) -> int | None:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "employees" and parts[2].isdigit():
        return int(parts[2])
    return None


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FaceAttendanceDashboard/1.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path in {"/login", "/login.html"}:
            session = self.get_authenticated_session()
            if session:
                self.redirect("/")
                return

            self.serve_file("login.html")
            return

        if parsed.path.lstrip("/") in PUBLIC_FRONTEND_FILES:
            self.serve_frontend(parsed.path)
            return

        if parsed.path.startswith("/api/"):
            if parsed.path == "/api/auth/session":
                self.handle_session_status()
                return

            if not self.require_auth(is_api=True):
                return

            self.handle_api(parsed)
            return

        if not self.require_auth(is_api=False):
            return

        self.serve_frontend(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/auth/login":
            self.handle_login()
            return

        if parsed.path == "/api/auth/logout":
            self.handle_logout()
            return

        if parsed.path.startswith("/api/") and not self.require_auth(is_api=True):
            return

        self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)

        if not parsed.path.startswith("/api/"):
            self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)
            return

        if not self.require_auth(is_api=True):
            return

        employee_id = extract_employee_id(parsed.path)
        if employee_id is None:
            self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)
            return

        self.handle_employee_delete(employee_id)

    def handle_api(self, parsed) -> None:
        data = get_dashboard_data()
        query = parse_qs(parsed.query)
        path = parsed.path

        if path == "/api/dashboard/summary":
            self.send_json({"summary": data["summary"]})
            return

        if path == "/api/employees":
            employees = build_employee_rows(data)
            search = first_query_value(query, "search")
            status_filter = first_query_value(query, "status")
            if search:
                employees = [employee for employee in employees if search.lower() in employee["name"].lower()]
            if status_filter:
                employees = [
                    employee
                    for employee in employees
                    if status_filter.lower() in employee["current_status"].lower()
                ]
            self.send_json({"employees": employees})
            return

        employee_id = extract_employee_id(path)
        if employee_id is not None:
            employee = get_employee_detail(employee_id, data)
            if employee is None:
                self.send_json({"error": "Employee not found."}, status=HTTPStatus.NOT_FOUND)
                return

            self.send_json({"employee": employee})
            return

        if path == "/api/attendance/today":
            name_query = first_query_value(query, "search")
            status_filter = first_query_value(query, "status")
            records = filter_records(data["today_records"], name_query=name_query, status_filter=status_filter)
            self.send_json({"records": records})
            return

        if path == "/api/attendance/history":
            name_query = first_query_value(query, "search")
            work_date = first_query_value(query, "date")
            status_filter = first_query_value(query, "status")
            records = filter_records(data["records"], name_query=name_query, work_date=work_date, status_filter=status_filter)
            self.send_json({"records": records})
            return

        if path == "/api/logs":
            name_query = first_query_value(query, "search")
            work_date = first_query_value(query, "date")
            status_filter = first_query_value(query, "status")
            events = filter_events(
                data["events"],
                name_query=name_query,
                work_date=work_date,
                status_filter=status_filter,
            )
            self.send_json({"logs": events})
            return

        if path == "/api/latest-detection":
            self.send_json({"latest_detection": data["latest_detection"]})
            return

        if path == "/api/status-rules":
            self.send_json(get_status_rules())
            return

        if path == "/api/health":
            self.send_json(
                {
                    "status": "ok",
                    "project_source_dir": str(PROJECT_SOURCE_DIR),
                    "frontend_dir": str(FRONTEND_DIR),
                }
            )
            return

        self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)

    def handle_login(self) -> None:
        payload = self.read_json_body()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        auth_settings = get_auth_settings()

        if not (
            hmac.compare_digest(username, auth_settings["username"])
            and hmac.compare_digest(password, auth_settings["password"])
        ):
            self.send_json(
                {"error": "Invalid username or password."},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return

        self.send_json(
            {"authenticated": True, "username": username},
            headers={"Set-Cookie": build_session_cookie(username)},
        )

    def handle_logout(self) -> None:
        self.send_json(
            {"authenticated": False},
            headers={"Set-Cookie": clear_session_cookie()},
        )

    def handle_session_status(self) -> None:
        session = self.get_authenticated_session()
        if session is None:
            self.send_json(
                {"authenticated": False, "error": "Authentication required."},
                status=HTTPStatus.UNAUTHORIZED,
                headers={"Set-Cookie": clear_session_cookie()},
            )
            return

        self.send_json({"authenticated": True, "username": session["username"]})

    def handle_employee_delete(self, employee_id: int) -> None:
        result = delete_employee_record(employee_id)
        if not result["deleted"]:
            self.send_json({"error": result["error"]}, status=HTTPStatus.NOT_FOUND)
            return

        message = f'{result["employee_name"]} was deleted successfully.'
        payload = {
            "deleted": True,
            "employee_id": result["employee_id"],
            "employee_name": result["employee_name"],
            "message": message,
        }
        if result.get("warning"):
            payload["warning"] = result["warning"]

        self.send_json(payload, status=HTTPStatus.OK)

    def get_authenticated_session(self) -> dict[str, str] | None:
        if hasattr(self, "_cached_session"):
            return self._cached_session

        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            self._cached_session = None
            return None

        cookies = SimpleCookie()
        cookies.load(cookie_header)
        morsel = cookies.get(SESSION_COOKIE_NAME)
        if morsel is None:
            self._cached_session = None
            return None

        self._cached_session = decode_session_token(morsel.value)
        return self._cached_session

    def require_auth(self, is_api: bool) -> bool:
        if self.get_authenticated_session() is not None:
            return True

        if is_api:
            self.send_json(
                {"error": "Authentication required."},
                status=HTTPStatus.UNAUTHORIZED,
                headers={"Set-Cookie": clear_session_cookie()},
            )
            return False

        self.redirect("/login", headers={"Set-Cookie": clear_session_cookie()})
        return False

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}

        raw_body = self.rfile.read(length)
        if not raw_body:
            return {}

        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        for header_name, header_value in (headers or {}).items():
            self.send_header(header_name, header_value)
        self.end_headers()

    def serve_file(self, filename: str) -> None:
        candidate = FRONTEND_DIR / filename
        if not candidate.exists() or candidate.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def serve_frontend(self, raw_path: str) -> None:
        relative_path = raw_path.strip("/") or "index.html"
        candidate = (FRONTEND_DIR / relative_path).resolve()

        if not str(candidate).startswith(str(FRONTEND_DIR.resolve())) or not candidate.exists() or candidate.is_dir():
            candidate = FRONTEND_DIR / "index.html"

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def send_json(
        self,
        payload,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for header_name, header_value in (headers or {}).items():
            self.send_header(header_name, header_value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Keep the console focused on meaningful server startup and errors.
        return


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def run() -> None:
    load_local_env()
    get_auth_settings()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard server running at http://{HOST}:{PORT}")
    print(f"Reading database and logs from: {PROJECT_SOURCE_DIR}")
    print(f"Admin login loaded from: {ENV_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run()
