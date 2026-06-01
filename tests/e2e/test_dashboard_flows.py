from __future__ import annotations

import json
import base64
from datetime import datetime

import numpy as np
import pytest


def _seed_dashboard_dataset():
    import database_utils

    ada_id = database_utils.insert_user(
        "Ada Lovelace",
        json.dumps([0.1, 0.2, 0.3]),
        photo_path="employee_images/user_1.jpg",
        department_role="Engineering",
    )
    bob_id = database_utils.insert_user("Bob Stone", json.dumps([0.4]), department_role="Support")
    database_utils.log_attendance_event("Ada Lovelace", "WARNING: Late (Morning)", datetime(2026, 5, 30, 9, 20))
    database_utils.log_attendance_event("Ada Lovelace", "CHECK-OUT", datetime(2026, 5, 30, 17, 45))
    database_utils.LOG_PATH.write_text(
        "30/05/2026 09:20:00 - Ada Lovelace - WARNING: Late (Morning)\n"
        "30/05/2026 17:45:00 - Ada Lovelace - CHECK-OUT\n",
        encoding="utf-8",
    )
    return ada_id, bob_id


def _login_cookie(client):
    status, headers, body = client.request(
        "POST",
        "/api/auth/login",
        {"username": "admin", "password": "secret1"},
    )
    assert status == 200, body.decode("utf-8")
    return headers["Set-Cookie"].split(";", 1)[0]


def _json(body):
    return json.loads(body.decode("utf-8"))


def _patch_successful_face_registration(app_module, monkeypatch, encoding=None):
    frame = np.zeros((48, 48, 3), dtype=np.uint8)
    encoding = np.array(encoding or [0.9, 0.8])

    class FakeCv2:
        IMREAD_COLOR = 1
        COLOR_BGR2RGB = 2

        @staticmethod
        def imdecode(image_array, mode):
            return frame

        @staticmethod
        def cvtColor(image, mode):
            return image

        @staticmethod
        def imwrite(path, image):
            return True

    class FakeFaceRecognition:
        @staticmethod
        def face_locations(image):
            return [(8, 30, 30, 8)]

        @staticmethod
        def face_encodings(image, locations):
            return [encoding]

        @staticmethod
        def face_distance(known_encodings, face_encoding):
            return np.array([0.9 for _ in known_encodings])

    monkeypatch.setattr(app_module, "cv2", FakeCv2)
    monkeypatch.setattr(app_module, "face_recognition", FakeFaceRecognition)


@pytest.mark.e2e
def test_dashboard_summary_flow(initialized_db, fixed_now):
    import data_access

    _seed_dashboard_dataset()
    data = data_access.get_dashboard_data()

    assert data["summary"]["total_registered_employees"] == 2
    assert data["summary"]["present_today"] == 1
    assert data["summary"]["absent_today"] == 1


@pytest.mark.e2e
def test_employee_rows_show_current_status(initialized_db, fixed_now):
    import data_access

    ada_id, bob_id = _seed_dashboard_dataset()
    rows = data_access.build_employee_rows(data_access.get_dashboard_data())

    by_id = {row["id"]: row for row in rows}
    assert by_id[ada_id]["current_status"] == "Checked Out"
    assert by_id[bob_id]["current_status"] == "Absent / No activity today"


@pytest.mark.e2e
def test_employee_detail_flow_counts_late_history(initialized_db, fixed_now):
    import data_access

    ada_id, _ = _seed_dashboard_dataset()
    detail = data_access.get_employee_detail(ada_id, data_access.get_dashboard_data())

    assert detail["name"] == "Ada Lovelace"
    assert detail["department_role"] == "Engineering"
    assert detail["late_history_count"] == 1


@pytest.mark.e2e
def test_attendance_filter_by_name_and_status(initialized_db, fixed_now):
    import data_access

    _seed_dashboard_dataset()
    records = data_access.get_dashboard_data()["records"]

    filtered = data_access.filter_records(records, name_query="ada", status_filter="checked out")

    assert len(filtered) == 1
    assert filtered[0]["employee_name"] == "Ada Lovelace"


@pytest.mark.e2e
def test_log_parser_flow_from_text_file(initialized_db, fixed_now):
    import data_access

    data_access.LOG_PATH.write_text(
        "30/05/2026 09:20:00 - Ada Lovelace - WARNING: Late (Morning)\n"
        "not parseable\n",
        encoding="utf-8",
    )

    events = data_access.parse_log_events()

    assert events[0]["employee_name"] == "Ada Lovelace"
    assert events[0]["status_group"] == "warning"
    assert events[1]["status"] == "UNPARSED"


@pytest.mark.e2e
def test_log_filter_flow(initialized_db, fixed_now):
    import data_access

    data_access.LOG_PATH.write_text(
        "30/05/2026 09:20:00 - Ada Lovelace - WARNING: Late (Morning)\n"
        "30/05/2026 18:05:00 - Bob Stone - CHECK-OUT (After 18:00)\n",
        encoding="utf-8",
    )

    events = data_access.parse_log_events()
    filtered = data_access.filter_events(events, status_filter="late")

    assert len(filtered) == 1
    assert filtered[0]["employee_name"] == "Ada Lovelace"


@pytest.mark.e2e
def test_csv_export_flow(initialized_db, fixed_now):
    import data_access

    _seed_dashboard_dataset()
    csv_bytes = data_access.attendance_records_to_csv(data_access.get_dashboard_data()["records"])

    assert csv_bytes.startswith("\ufeff".encode("utf-8"))
    assert b"Ada Lovelace" in csv_bytes


@pytest.mark.e2e
def test_report_daily_weekly_monthly_late_absent_flow(initialized_db, fixed_now):
    import data_access

    _seed_dashboard_dataset()
    data = data_access.get_dashboard_data()

    assert len(data_access.build_report_records("daily", data["records"], data["users"])) == 1
    assert len(data_access.build_report_records("weekly", data["records"], data["users"])) == 1
    assert len(data_access.build_report_records("monthly", data["records"], data["users"])) == 1
    assert len(data_access.build_report_records("late", data["records"], data["users"])) == 1
    assert data_access.build_report_records("absent", data["records"], data["users"])[0]["employee_name"] == "Bob Stone"


@pytest.mark.e2e
def test_unknown_face_dashboard_flow(initialized_db, fixed_now):
    import database_utils

    face_id = database_utils.record_unknown_face("unknown_face_images/unknown.jpg")
    faces = database_utils.load_unknown_faces()
    face = database_utils.get_unknown_face(face_id)

    assert faces[0]["image_url"] == "/unknown_face_images/unknown.jpg"
    assert face["detection_count"] == 1


@pytest.mark.e2e
def test_admin_audit_flow(initialized_db, fixed_now):
    import database_utils

    database_utils.create_admin_account("admin", "secret1")
    database_utils.write_admin_log("admin", "EXPORT_DOWNLOADED", "CSV export")

    assert database_utils.verify_admin_credentials("admin", "secret1")
    assert database_utils.read_admin_logs()[0]["action_type"] == "EXPORT_DOWNLOADED"


@pytest.mark.e2e
def test_e1_successful_admin_login_redirects_to_dashboard(dashboard_server):
    cookie = _login_cookie(dashboard_server)

    status, headers, _ = dashboard_server.request(
        "GET",
        "/login",
        cookie=cookie,
        follow_redirects=False,
    )

    assert status == 303
    assert headers["Location"] == "/"


@pytest.mark.e2e
def test_e2_invalid_credentials_show_error_and_block_access(dashboard_server):
    status, _, body = dashboard_server.request(
        "POST",
        "/api/auth/login",
        {"username": "admin", "password": "wrong"},
    )

    assert status == 401
    assert _json(body)["error"] == "Invalid username or password."


@pytest.mark.e2e
def test_e3_unauthenticated_protected_page_redirects_to_login(dashboard_server):
    status, headers, _ = dashboard_server.request(
        "GET",
        "/",
        follow_redirects=False,
    )

    assert status == 303
    assert headers["Location"] == "/login"


@pytest.mark.e2e
def test_e4_register_employee_via_upload_appears_in_list(dashboard_server, dashboard_app, monkeypatch):
    _patch_successful_face_registration(dashboard_app, monkeypatch)
    cookie = _login_cookie(dashboard_server)
    image = "data:image/jpeg;base64," + base64.b64encode(b"fake-image").decode("ascii")

    status, _, body = dashboard_server.request(
        "POST",
        "/api/employees/register",
        {"name": "Upload Person", "department_role": "QA", "image": image},
        cookie=cookie,
    )
    assert status == 200, body.decode("utf-8")

    status, _, body = dashboard_server.request("GET", "/api/employees", cookie=cookie)
    employees = _json(body)["employees"]

    assert status == 200
    assert any(employee["name"] == "Upload Person" for employee in employees)


@pytest.mark.e2e
def test_e5_duplicate_registration_is_rejected_with_message(dashboard_server):
    import database_utils

    database_utils.insert_user("Ada Lovelace", json.dumps([0.1, 0.2]))
    cookie = _login_cookie(dashboard_server)

    status, _, body = dashboard_server.request(
        "POST",
        "/api/employees/register",
        {"name": "ada lovelace", "image": "data:image/jpeg;base64,ZmFrZQ=="},
        cookie=cookie,
    )

    assert status == 409
    assert "already registered" in _json(body)["error"]


@pytest.mark.e2e
def test_e7_csv_export_downloads_with_expected_header_row(dashboard_server, fixed_now):
    _seed_dashboard_dataset()
    cookie = _login_cookie(dashboard_server)

    status, headers, body = dashboard_server.request(
        "GET",
        "/api/attendance/export?format=csv",
        cookie=cookie,
    )

    first_line = body.decode("utf-8-sig").splitlines()[0]
    assert status == 200
    assert headers["Content-Type"].startswith("text/csv")
    assert first_line == "Employee ID,Employee Name,Date,Entry Time,Exit Time,Current Status,Event Type,Notes"


@pytest.mark.e2e
def test_e8_excel_export_downloads_valid_xlsx_file(dashboard_server, dashboard_app, monkeypatch, fixed_now):
    _seed_dashboard_dataset()
    monkeypatch.setattr(dashboard_app, "attendance_records_to_xlsx", lambda records: b"PK\x03\x04fake-xlsx")
    cookie = _login_cookie(dashboard_server)

    status, headers, body = dashboard_server.request(
        "GET",
        "/api/attendance/export?format=xlsx",
        cookie=cookie,
    )

    assert status == 200
    assert headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert body.startswith(b"PK")


@pytest.mark.e2e
def test_e9_manual_checkin_checkout_updates_employee_record(dashboard_server, fixed_now):
    import database_utils

    employee_id = database_utils.insert_user("Manual Person", json.dumps([0.1]))
    cookie = _login_cookie(dashboard_server)

    checkin_status, _, _ = dashboard_server.request(
        "POST",
        f"/api/employees/{employee_id}/checkin",
        cookie=cookie,
    )
    checkout_status, _, _ = dashboard_server.request(
        "POST",
        f"/api/employees/{employee_id}/checkout",
        cookie=cookie,
    )

    with database_utils.get_connection() as connection:
        row = connection.execute(
            "SELECT entry_time, exit_time FROM attendance_logs WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()

    assert checkin_status == 200
    assert checkout_status == 200
    assert row["entry_time"] == "09:20:00"
    assert row["exit_time"] == "09:20:00"


@pytest.mark.e2e
def test_e10_delete_employee_returns_confirmation_and_removes_row(dashboard_server):
    import database_utils

    employee_id = database_utils.insert_user("Delete Via API", json.dumps([0.1]))
    cookie = _login_cookie(dashboard_server)

    status, _, body = dashboard_server.request(
        "DELETE",
        f"/api/employees/{employee_id}",
        cookie=cookie,
    )

    with database_utils.get_connection() as connection:
        employee = connection.execute(
            "SELECT id FROM employees WHERE id = ?",
            (employee_id,),
        ).fetchone()

    payload = _json(body)
    assert status == 200
    assert payload["deleted"] is True
    assert "was deleted successfully" in payload["message"]
    assert employee is None
