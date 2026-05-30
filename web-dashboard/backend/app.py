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
        attendance_records_to_csv,
        attendance_records_to_xlsx,
        build_employee_rows,
        build_export_filename,
        build_report_records,
        build_xlsx_filename,
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
        attendance_records_to_csv,
        attendance_records_to_xlsx,
        build_employee_rows,
        build_export_filename,
        build_report_records,
        build_xlsx_filename,
        filter_events,
        filter_records,
        get_dashboard_data,
        get_employee_detail,
        get_status_rules,
        json_bytes,
    )

if str(PROJECT_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE_DIR))

try:
    import cv2
    import face_recognition
    import numpy as np
except ImportError:
    cv2 = face_recognition = np = None  # type: ignore[assignment]

from database_utils import (
    create_admin_account,
    delete_employee_record,
    employee_name_exists,
    ensure_admin_account,
    get_attendance_rules,
    get_unknown_face,
    insert_user,
    init_db,
    load_registered_faces,
    load_unknown_faces,
    log_manual_event,
    read_admin_accounts,
    read_admin_logs,
    record_unknown_face,
    update_attendance_rules,
    update_employee_data,
    update_employee_photo,
    verify_admin_credentials,
    write_admin_log,
)
from time_override import clear_time_override, read_time_override, set_time_override

try:
    from attendance_station import AttendanceStation
except ImportError:
    AttendanceStation = None  # type: ignore[assignment,misc]


HOST = "127.0.0.1"
PORT = 8000
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
ENV_PATH = PROJECT_SOURCE_DIR / ".env"
SESSION_COOKIE_NAME = "dashboard_session"
SESSION_DURATION_SECONDS = 60 * 60 * 8
PUBLIC_FRONTEND_FILES = {"styles.css"}
CAMERA_STATION = AttendanceStation() if AttendanceStation is not None else None


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


def seed_env_admin() -> None:
    auth_settings = get_auth_settings()
    if auth_settings["username"] and auth_settings["password"]:
        ensure_admin_account(auth_settings["username"], auth_settings["password"])


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


def extract_unknown_face_id(path: str) -> int | None:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "unknown-faces" and parts[2].isdigit():
        return int(parts[2])
    return None


def extract_employee_event(path: str) -> tuple[int, str] | None:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "employees" and parts[2].isdigit():
        if parts[3] == "checkin":
            return int(parts[2]), "CHECK-IN"
        if parts[3] == "checkout":
            return int(parts[2]), "CHECK-OUT"
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

        if parsed.path.lstrip("/") in PUBLIC_FRONTEND_FILES or parsed.path.startswith("/assets/"):
            self.serve_frontend(parsed.path)
            return

        if parsed.path.startswith("/employee_images/"):
            if not self.require_auth(is_api=False):
                return
            self.serve_employee_image(parsed.path)
            return

        if parsed.path.startswith("/unknown_face_images/"):
            if not self.require_auth(is_api=False):
                return
            self.serve_unknown_face_image(parsed.path)
            return

        if parsed.path == "/api/camera-station/feed":
            if not self.require_auth(is_api=False):
                return
            self.stream_camera_feed()
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

        if parsed.path == "/api/employees/register":
            self.handle_employee_register()
            return

        if parsed.path == "/api/camera-station/start":
            self.handle_camera_station_start()
            return

        if parsed.path == "/api/camera-station/stop":
            self.handle_camera_station_stop()
            return

        if parsed.path == "/api/test-time":
            self.handle_test_time_set()
            return

        if parsed.path == "/api/test-time/clear":
            self.handle_test_time_clear()
            return

        if parsed.path == "/api/attendance-rules":
            self.handle_attendance_rules_update()
            return

        if parsed.path == "/api/admins":
            self.handle_admin_create()
            return

        employee_event = extract_employee_event(parsed.path)
        if employee_event is not None:
            self.handle_manual_event(*employee_event)
            return

        self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)

        if not parsed.path.startswith("/api/"):
            self.send_json({"error": "Endpoint not found."}, status=HTTPStatus.NOT_FOUND)
            return

        if not self.require_auth(is_api=True):
            return

        employee_id = extract_employee_id(parsed.path)
        if employee_id is not None:
            self.handle_employee_edit(employee_id)
            return

        if parsed.path == "/api/attendance-rules":
            self.handle_attendance_rules_update()
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

        if path == "/api/attendance/export":
            name_query = first_query_value(query, "search")
            work_date = first_query_value(query, "date")
            status_filter = first_query_value(query, "status")
            records = filter_records(
                data["records"],
                name_query=name_query,
                work_date=work_date,
                status_filter=status_filter,
            )
            fmt = first_query_value(query, "format") or "csv"
            if fmt == "xlsx":
                xlsx_bytes = attendance_records_to_xlsx(records)
                if xlsx_bytes is None:
                    self.send_json({"error": "openpyxl is not installed on this server."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                filename = build_xlsx_filename("all", work_date)
                self.send_xlsx(xlsx_bytes, filename)
                session = self.get_authenticated_session()
                username = session["username"] if session else "unknown"
                write_admin_log(username, "EXPORT_DOWNLOADED", f"Excel export: {filename}")
            else:
                csv_bytes = attendance_records_to_csv(records)
                filename = build_export_filename(work_date)
                self.send_csv(csv_bytes, filename)
                session = self.get_authenticated_session()
                username = session["username"] if session else "unknown"
                write_admin_log(username, "EXPORT_DOWNLOADED", f"CSV export: {filename}")
            return

        if path == "/api/reports/export":
            report_type = first_query_value(query, "type") or "all"
            fmt = first_query_value(query, "format") or "xlsx"
            records = build_report_records(report_type, data["records"], data["users"])
            if fmt == "csv":
                csv_bytes = attendance_records_to_csv(records)
                filename = build_export_filename(None).replace("attendance_export", f"report_{report_type}")
                self.send_csv(csv_bytes, filename)
            else:
                xlsx_bytes = attendance_records_to_xlsx(records)
                if xlsx_bytes is None:
                    self.send_json({"error": "openpyxl is not installed on this server."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                filename = build_xlsx_filename(report_type)
                self.send_xlsx(xlsx_bytes, filename)
            session = self.get_authenticated_session()
            username = session["username"] if session else "unknown"
            write_admin_log(username, "EXPORT_DOWNLOADED", f"Report export: {report_type} as {fmt}")
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

        if path == "/api/camera-station/status":
            if CAMERA_STATION is None:
                self.send_json(
                    {
                        "camera_index": 0,
                        "online": False,
                        "worker_running": False,
                        "last_error": "Camera station dependencies are not available.",
                        "known_faces": 0,
                    }
                )
                return

            self.send_json({"station": CAMERA_STATION.status()})
            return

        if path == "/api/status-rules":
            self.send_json(get_status_rules())
            return

        if path == "/api/attendance-rules":
            self.send_json({"rules": get_attendance_rules()})
            return

        if path == "/api/unknown-faces":
            faces = load_unknown_faces()
            self.send_json({"unknown_faces": faces})
            return

        unknown_face_id = extract_unknown_face_id(path)
        if unknown_face_id is not None:
            face = get_unknown_face(unknown_face_id)
            if face is None:
                self.send_json({"error": "Unknown face record not found."}, status=HTTPStatus.NOT_FOUND)
                return
            self.send_json({"face": face})
            return

        if path == "/api/admin-logs":
            logs = read_admin_logs()
            self.send_json({"logs": logs})
            return

        if path == "/api/admins":
            self.send_json({"admins": read_admin_accounts()})
            return

        if path == "/api/test-time":
            self.send_json({"test_time": read_time_override()})
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

    def handle_camera_station_start(self) -> None:
        if CAMERA_STATION is None:
            self.send_json({"error": "Camera station dependencies are not available."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        CAMERA_STATION.start()
        self.write_current_admin_log("CAMERA_STARTED", "Attendance camera station started")
        self.send_json({"station": CAMERA_STATION.status()})

    def handle_camera_station_stop(self) -> None:
        if CAMERA_STATION is None:
            self.send_json({"error": "Camera station dependencies are not available."}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        CAMERA_STATION.stop()
        self.write_current_admin_log("CAMERA_STOPPED", "Attendance camera station stopped")
        self.send_json({"station": CAMERA_STATION.status()})

    def handle_test_time_set(self) -> None:
        payload = self.read_json_body()
        scenario_key = str(payload.get("scenario_key", "")).strip()
        try:
            test_time = set_time_override(scenario_key)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.write_current_admin_log("TEST_TIME_SET", f"Scenario: {scenario_key}")
        self.send_json({"test_time": test_time})

    def handle_test_time_clear(self) -> None:
        self.write_current_admin_log("TEST_TIME_CLEARED", "Returned to real system time")
        self.send_json({"test_time": clear_time_override()})

    def handle_login(self) -> None:
        payload = self.read_json_body()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        if not verify_admin_credentials(username, password):
            self.send_json(
                {"error": "Invalid username or password."},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return

        try:
            write_admin_log(username, "LOGIN", "Admin logged in")
        except Exception:
            pass

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

    def handle_employee_register(self) -> None:
        if cv2 is None:
            self.send_json({"error": "Face recognition library not available."}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        payload = self.read_json_body()
        name = str(payload.get("name", "")).strip()
        department_role = str(payload.get("department_role", "")).strip() or None
        image_data_url = str(payload.get("image", ""))

        if not name:
            self.send_json({"error": "Employee name is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        # Check 1: name uniqueness (case-insensitive)
        existing_name = employee_name_exists(name)
        if existing_name:
            self.send_json(
                {"error": f"An employee named '{existing_name}' is already registered."},
                status=HTTPStatus.CONFLICT,
            )
            return

        if not image_data_url or "," not in image_data_url:
            self.send_json({"error": "Image data is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            image_bytes = base64.b64decode(image_data_url.split(",", 1)[1])
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("Could not decode image data.")
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception as exc:
            self.send_json({"error": f"Image decoding failed: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            return

        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        if not face_encodings:
            self.send_json(
                {"error": "No face detected in the captured photo. Please retake."},
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
            return

        # Check 2: face encoding similarity against all registered faces
        known_encodings, known_names = load_registered_faces()
        if known_encodings:
            distances = face_recognition.face_distance(known_encodings, face_encodings[0])
            best_idx = int(distances.argmin())
            best_distance = float(distances[best_idx])
            if best_distance < 0.6:
                matched_name = known_names[best_idx]
                similarity = round((1 - best_distance) * 100)
                self.send_json(
                    {"error": f"Bu yüz zaten '{matched_name}' olarak kayıtlı (benzerlik: %{similarity})."},
                    status=HTTPStatus.CONFLICT,
                )
                return

        encoding_json = json.dumps(face_encodings[0].tolist())
        user_id = insert_user(name, encoding_json, department_role=department_role)

        images_dir = PROJECT_SOURCE_DIR / "employee_images"
        images_dir.mkdir(exist_ok=True)

        top, right, bottom, left = face_locations[0]
        h, w = frame.shape[:2]
        pad = 60
        face_img = frame[max(0, top - pad):min(h, bottom + pad), max(0, left - pad):min(w, right + pad)]

        image_filename = f"user_{user_id}.jpg"
        cv2.imwrite(str(images_dir / image_filename), face_img)

        relative_path = f"employee_images/{image_filename}"
        update_employee_photo(user_id, relative_path)

        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        try:
            write_admin_log(username, "EMPLOYEE_CREATED", f"Registered: {name} (ID: {user_id})")
        except Exception:
            pass

        self.send_json({
            "success": True,
            "user_id": user_id,
            "name": name,
            "department_role": department_role,
            "image_url": f"/employee_images/{image_filename}",
        })

    def handle_manual_event(self, employee_id: int, event_type: str) -> None:
        result = log_manual_event(employee_id, event_type)
        if not result["success"]:
            self.send_json({"error": result["error"]}, status=HTTPStatus.NOT_FOUND)
            return
        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        action = "MANUAL_CHECKIN" if event_type == "CHECK-IN" else "MANUAL_CHECKOUT"
        try:
            write_admin_log(username, action, f"{result['employee_name']} (ID: {employee_id})")
        except Exception:
            pass
        self.send_json(result)

    def handle_employee_delete(self, employee_id: int) -> None:
        result = delete_employee_record(employee_id)
        if not result["deleted"]:
            self.send_json({"error": result["error"]}, status=HTTPStatus.NOT_FOUND)
            return

        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        try:
            write_admin_log(username, "EMPLOYEE_DELETED", f"Deleted: {result['employee_name']} (ID: {employee_id})")
        except Exception:
            pass

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

    def handle_employee_edit(self, employee_id: int) -> None:
        payload = self.read_json_body()
        full_name = str(payload.get("full_name", "")).strip() or None
        department_role = payload.get("department_role")
        if department_role is not None:
            department_role = str(department_role).strip()
        status = str(payload.get("status", "")).strip() or None

        result = update_employee_data(employee_id, full_name=full_name, department_role=department_role, status=status)
        if not result["success"]:
            self.send_json({"error": result["error"]}, status=HTTPStatus.NOT_FOUND)
            return

        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        changes = ", ".join(
            f"{k}={v}"
            for k, v in {"name": full_name, "role": department_role, "status": status}.items()
            if v is not None
        )
        try:
            write_admin_log(username, "EMPLOYEE_EDITED", f"ID: {employee_id} — {changes}")
        except Exception:
            pass

        self.send_json({"success": True, "employee_id": employee_id})

    def handle_attendance_rules_update(self) -> None:
        payload = self.read_json_body()
        rules = {k: str(v).strip() for k, v in payload.items() if isinstance(v, str)}
        update_attendance_rules(rules)
        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        try:
            write_admin_log(username, "RULES_UPDATED", f"Attendance rules updated: {rules}")
        except Exception:
            pass
        self.send_json({"success": True, "rules": get_attendance_rules()})

    def handle_admin_create(self) -> None:
        payload = self.read_json_body()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))

        result = create_admin_account(username, password)
        if not result["success"]:
            status = HTTPStatus.CONFLICT if "already exists" in result["error"] else HTTPStatus.BAD_REQUEST
            self.send_json({"error": result["error"]}, status=status)
            return

        session = self.get_authenticated_session()
        current_admin = session["username"] if session else "unknown"
        try:
            write_admin_log(current_admin, "ADMIN_CREATED", f"Created admin: {username}")
        except Exception:
            pass

        self.send_json(result, status=HTTPStatus.CREATED)

    def write_current_admin_log(self, action_type: str, details: str | None = None) -> None:
        session = self.get_authenticated_session()
        username = session["username"] if session else "unknown"
        try:
            write_admin_log(username, action_type, details)
        except Exception:
            pass

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

    def serve_employee_image(self, raw_path: str) -> None:
        relative_path = raw_path.lstrip("/")
        candidate = (PROJECT_SOURCE_DIR / relative_path).resolve()
        employee_images_dir = (PROJECT_SOURCE_DIR / "employee_images").resolve()

        try:
            candidate.relative_to(employee_images_dir)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not candidate.exists() or candidate.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "image/jpeg")
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def serve_unknown_face_image(self, raw_path: str) -> None:
        relative_path = raw_path.lstrip("/")
        candidate = (PROJECT_SOURCE_DIR / relative_path).resolve()
        unknown_images_dir = (PROJECT_SOURCE_DIR / "unknown_face_images").resolve()

        try:
            candidate.relative_to(unknown_images_dir)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not candidate.exists() or candidate.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "image/jpeg")
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(candidate.read_bytes())

    def stream_camera_feed(self) -> None:
        if CAMERA_STATION is None:
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Camera station is unavailable.")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        version = -1
        try:
            while True:
                version, jpeg = CAMERA_STATION.wait_for_frame(version)
                if not jpeg:
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

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

    def send_csv(
        self,
        body: bytes,
        filename: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_xlsx(
        self,
        body: bytes,
        filename: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
    load_local_env()
    get_auth_settings()
    init_db()
    seed_env_admin()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard server running at http://{HOST}:{PORT}")
    print(f"Reading database and logs from: {PROJECT_SOURCE_DIR}")
    print(f"Admin login loaded from: {ENV_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run()
