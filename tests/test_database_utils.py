from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta


def test_init_db_creates_core_tables(initialized_db):
    import database_utils

    with sqlite3.connect(database_utils.DB_PATH) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert {"users", "employees", "attendance_logs", "admins", "settings", "unknown_faces", "admin_activity_log"} <= tables


def test_admin_password_hash_verification():
    import database_utils

    password_hash = database_utils.hash_admin_password("strongpass")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert database_utils.verify_admin_password("strongpass", password_hash)
    assert not database_utils.verify_admin_password("wrongpass", password_hash)
    assert not database_utils.verify_admin_password("strongpass", "bad-format")


def test_create_verify_and_list_admin(initialized_db):
    import database_utils

    created = database_utils.create_admin_account("admin", "secret1")
    duplicate = database_utils.create_admin_account("admin", "secret1")

    assert created["success"] is True
    assert duplicate["success"] is False
    assert database_utils.verify_admin_credentials("admin", "secret1")
    assert not database_utils.verify_admin_credentials("admin", "wrong")
    assert database_utils.read_admin_accounts() == [{"id": 1, "username": "admin"}]


def test_insert_user_syncs_employee_and_detects_name(initialized_db):
    import database_utils

    user_id = database_utils.insert_user(
        "Ada Lovelace",
        json.dumps([0.1, 0.2, 0.3]),
        photo_path="employee_images/user_1.jpg",
        department_role="Engineering",
    )

    assert user_id == 1
    assert database_utils.employee_name_exists("ada lovelace") == "Ada Lovelace"
    records = database_utils.fetch_registered_users()
    assert [(row["id"], row["name"]) for row in records] == [(1, "Ada Lovelace")]


def test_load_registered_faces_returns_vectors(initialized_db):
    import database_utils

    database_utils.insert_user("Grace Hopper", json.dumps([0.4, 0.5, 0.6]))

    encodings, names = database_utils.load_registered_faces()

    assert names == ["Grace Hopper"]
    assert encodings[0].tolist() == [0.4, 0.5, 0.6]


def test_attendance_upsert_keeps_earliest_entry_latest_exit(initialized_db):
    import database_utils

    employee_id = database_utils.insert_user("Alan Turing", json.dumps([1.0, 2.0]))

    database_utils.log_attendance_event("Alan Turing", "WARNING: Late (Morning)", datetime(2026, 5, 30, 9, 20))
    database_utils.log_attendance_event("Alan Turing", "CHECK-IN", datetime(2026, 5, 30, 8, 55))
    database_utils.log_attendance_event("Alan Turing", "CHECK-OUT", datetime(2026, 5, 30, 17, 0))
    database_utils.log_attendance_event("Alan Turing", "CHECK-OUT (After 18:00)", datetime(2026, 5, 30, 18, 10))

    with database_utils.get_connection() as connection:
        row = connection.execute(
            "SELECT employee_id, entry_time, exit_time, attendance_status FROM attendance_logs"
        ).fetchone()
        row_count = connection.execute(
            "SELECT COUNT(*) FROM attendance_logs WHERE employee_id = ? AND date = ?",
            (employee_id, "2026-05-30"),
        ).fetchone()[0]

    assert row["employee_id"] == employee_id
    assert row["entry_time"] == "08:55:00"
    assert row["exit_time"] == "18:10:00"
    assert row["attendance_status"] == "late"
    assert row_count == 1


def test_manual_event_writes_db_and_text_log(initialized_db, fixed_now):
    import database_utils

    employee_id = database_utils.insert_user("Katherine Johnson", json.dumps([1]))
    result = database_utils.log_manual_event(employee_id, "CHECK-IN")

    assert result["success"] is True
    assert "Katherine Johnson - CHECK-IN (Manual)" in database_utils.LOG_PATH.read_text(encoding="utf-8")


def test_delete_employee_removes_rows_and_managed_photo(initialized_db):
    import database_utils

    images_dir = database_utils.PROJECT_ROOT / "employee_images"
    images_dir.mkdir()
    photo = images_dir / "user_1.jpg"
    photo.write_text("fake image", encoding="utf-8")

    employee_id = database_utils.insert_user("Delete Me", json.dumps([1]), photo_path="employee_images/user_1.jpg")
    database_utils.log_attendance_event("Delete Me", "CHECK-IN", datetime(2026, 5, 30, 8, 0))

    result = database_utils.delete_employee_record(employee_id)

    assert result["deleted"] is True
    assert result["deleted_attendance_rows"] == 1
    assert not photo.exists()


def test_unknown_faces_are_grouped_then_split(initialized_db, monkeypatch):
    import database_utils

    base = datetime(2026, 5, 30, 10, 0)
    times = iter([base, base + timedelta(seconds=10), base + timedelta(seconds=311)])
    monkeypatch.setattr(database_utils, "get_current_datetime", lambda: next(times))

    first = database_utils.record_unknown_face("unknown_face_images/one.jpg")
    second = database_utils.record_unknown_face("unknown_face_images/two.jpg")
    third = database_utils.record_unknown_face("unknown_face_images/three.jpg")

    faces = database_utils.load_unknown_faces()
    assert first == second
    assert third != first
    assert len(faces) == 2
    assert {face["detection_count"] for face in faces} == {1, 2}


def test_attendance_rules_and_admin_logs(initialized_db, fixed_now):
    import database_utils

    database_utils.update_attendance_rules({"late_warning": "09:10", "ignored": "00:00"})
    database_utils.write_admin_log("admin", "RULES_UPDATED", "changed warning")

    rules = database_utils.get_attendance_rules()
    logs = database_utils.read_admin_logs()

    assert rules["late_warning"] == "09:10"
    assert "ignored" not in rules
    assert logs[0]["action_type"] == "RULES_UPDATED"


def test_load_todays_attendance_state(initialized_db, fixed_now):
    import database_utils

    database_utils.insert_user("Today Person", json.dumps([2]))
    database_utils.log_attendance_event("Today Person", "CHECK-IN", datetime(2026, 5, 30, 8, 45))

    state = database_utils.load_todays_attendance_state()

    assert state["Today Person"]["type"] == "CHECK-IN"
    assert state["Today Person"]["time"].hour == 8


def test_update_employee_data_changes_user_and_employee(initialized_db):
    import database_utils

    employee_id = database_utils.insert_user("Old Name", json.dumps([1]))
    result = database_utils.update_employee_data(employee_id, full_name="New Name", department_role="HR", status="inactive")

    assert result == {"success": True, "employee_id": employee_id}
    assert database_utils.employee_name_exists("new name") == "New Name"


def test_determine_event_type_maps_checkin_checkout_and_overtime_statuses():
    import database_utils

    assert database_utils.determine_event_type("CHECK-IN") == "CHECK-IN"
    assert database_utils.determine_event_type("WARNING: Late (Morning)") == "CHECK-IN"
    assert database_utils.determine_event_type("CHECK-OUT") == "CHECK-OUT"
    assert database_utils.determine_event_type("CHECK-OUT (After 18:00)") == "CHECK-OUT"
    assert database_utils.determine_event_type("OVERTIME: 9.5 hours") == "CHECK-OUT"
