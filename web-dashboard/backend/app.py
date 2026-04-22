from __future__ import annotations

import mimetypes
from http import HTTPStatus
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


HOST = "127.0.0.1"
PORT = 8000
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FaceAttendanceDashboard/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return

        self.serve_frontend(parsed.path)

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

        if path.startswith("/api/employees/"):
            employee_id_str = path.rsplit("/", 1)[-1]
            if not employee_id_str.isdigit():
                self.send_json({"error": "Employee id must be numeric."}, status=HTTPStatus.BAD_REQUEST)
                return

            employee = get_employee_detail(int(employee_id_str), data)
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

    def serve_frontend(self, raw_path: str) -> None:
        relative_path = raw_path.strip("/") or "index.html"
        candidate = (FRONTEND_DIR / relative_path).resolve()

        if not str(candidate).startswith(str(FRONTEND_DIR.resolve())) or not candidate.exists() or candidate.is_dir():
            candidate = FRONTEND_DIR / "index.html"

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def send_json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Keep the console focused on meaningful server startup and errors.
        return


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard server running at http://{HOST}:{PORT}")
    print(f"Reading database and logs from: {PROJECT_SOURCE_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    run()
