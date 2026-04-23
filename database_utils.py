from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "face_records.db"
LOG_PATH = PROJECT_ROOT / "attendance_logs.txt"
LOG_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                face_vector TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
                photo_path TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date DATE NOT NULL,
                entry_time TIME,
                exit_time TIME,
                attendance_status TEXT NOT NULL DEFAULT 'on_time'
                    CHECK (attendance_status IN ('on_time', 'late', 'absent')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees(id),
                UNIQUE(employee_id, date)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_attendance_logs_employee_date
            ON attendance_logs(employee_id, date)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_employees_full_name
            ON employees(full_name)
            """
        )

        migrate_users_to_employees(cursor)
        migrate_text_logs_to_attendance(cursor)
        connection.commit()


def migrate_users_to_employees(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        INSERT INTO employees (id, full_name, created_at, status, photo_path)
        SELECT u.id, u.name, CURRENT_TIMESTAMP, 'active', NULL
        FROM users AS u
        LEFT JOIN employees AS e ON e.id = u.id
        WHERE e.id IS NULL
        """
    )

    cursor.execute(
        """
        UPDATE employees
        SET full_name = (
            SELECT users.name
            FROM users
            WHERE users.id = employees.id
        )
        WHERE id IN (SELECT id FROM users)
          AND full_name != (
            SELECT users.name
            FROM users
            WHERE users.id = employees.id
        )
        """
    )


def migrate_text_logs_to_attendance(cursor: sqlite3.Cursor) -> None:
    if not LOG_PATH.exists():
        return

    for raw_line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split(" - ", 2)
        if len(parts) != 3:
            continue

        timestamp_str, employee_name, status = parts

        try:
            event_dt = datetime.strptime(timestamp_str.strip(), LOG_DATETIME_FORMAT)
        except ValueError:
            continue

        employee_id = get_employee_id_by_name(cursor, employee_name.strip())
        if employee_id is None:
            continue

        upsert_attendance_log(cursor, employee_id, status.strip(), event_dt)


def load_registered_faces() -> tuple[list[Any], list[str]]:
    import json
    import numpy as np

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name, face_vector FROM users")
        rows = cursor.fetchall()

    known_encodings = []
    known_names = []

    for row in rows:
        known_names.append(row["name"])
        known_encodings.append(np.array(json.loads(row["face_vector"])))

    return known_encodings, known_names


def insert_user(name: str, face_vector_json: str, photo_path: str | None = None) -> int:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO users (name, face_vector) VALUES (?, ?)", (name, face_vector_json))
        user_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO employees (id, full_name, status, photo_path)
            VALUES (?, ?, 'active', ?)
            ON CONFLICT(id) DO UPDATE SET
                full_name = excluded.full_name,
                status = 'active',
                photo_path = COALESCE(excluded.photo_path, employees.photo_path)
            """,
            (user_id, name, photo_path),
        )
        connection.commit()
        return user_id


def fetch_registered_users() -> list[sqlite3.Row]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, name FROM users ORDER BY id")
        return cursor.fetchall()


def get_registered_user(cursor: sqlite3.Cursor, user_id: int) -> sqlite3.Row | None:
    cursor.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


def get_employee(cursor: sqlite3.Cursor, user_id: int) -> sqlite3.Row | None:
    cursor.execute("SELECT id, full_name, photo_path FROM employees WHERE id = ?", (user_id,))
    return cursor.fetchone()


def resolve_managed_file_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None

    candidate = Path(path_value.strip())
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError:
        return None

    return candidate


def delete_employee_record(user_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.cursor()
        user = get_registered_user(cursor, user_id)
        employee = get_employee(cursor, user_id)

        if user is None and employee is None:
            return {"deleted": False, "error": "Employee record was not found."}

        employee_name = (
            employee["full_name"]
            if employee is not None and employee["full_name"]
            else user["name"]
            if user is not None
            else f"Employee {user_id}"
        )
        photo_candidate = resolve_managed_file_path(employee["photo_path"] if employee is not None else None)

        cursor.execute("DELETE FROM attendance_logs WHERE employee_id = ?", (user_id,))
        deleted_attendance_rows = cursor.rowcount
        cursor.execute("DELETE FROM employees WHERE id = ?", (user_id,))
        deleted_employee_rows = cursor.rowcount
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted_user_rows = cursor.rowcount
        connection.commit()

    deleted_photo_path = None
    photo_warning = None

    if photo_candidate and photo_candidate.exists() and photo_candidate.is_file():
        try:
            photo_candidate.unlink()
            deleted_photo_path = str(photo_candidate)
        except OSError as exc:
            photo_warning = f"Employee data was deleted, but the photo file could not be removed: {exc}"

    return {
        "deleted": True,
        "employee_id": user_id,
        "employee_name": employee_name,
        "deleted_attendance_rows": deleted_attendance_rows,
        "deleted_user_rows": deleted_user_rows,
        "deleted_employee_rows": deleted_employee_rows,
        "deleted_photo_path": deleted_photo_path,
        "warning": photo_warning,
    }


def deactivate_or_delete_user(user_id: int) -> bool:
    return bool(delete_employee_record(user_id)["deleted"])


def log_attendance_event(name: str, status: str, event_dt: datetime) -> int | None:
    with get_connection() as connection:
        cursor = connection.cursor()
        employee_id = get_employee_id_by_name(cursor, name)
        if employee_id is None:
            return None

        upsert_attendance_log(cursor, employee_id, status, event_dt)
        connection.commit()
        return employee_id


def get_employee_id_by_name(cursor: sqlite3.Cursor, name: str) -> int | None:
    cursor.execute("SELECT id FROM employees WHERE full_name = ? ORDER BY id LIMIT 1", (name,))
    employee = cursor.fetchone()
    if employee is not None:
        cursor.execute("UPDATE employees SET status = 'active' WHERE id = ?", (employee["id"],))
        return int(employee["id"])

    cursor.execute("SELECT id FROM users WHERE name = ? ORDER BY id LIMIT 1", (name,))
    user = cursor.fetchone()
    if user is None:
        return None

    cursor.execute(
        """
        INSERT INTO employees (id, full_name, status)
        VALUES (?, ?, 'active')
        ON CONFLICT(id) DO UPDATE SET
            full_name = excluded.full_name,
            status = 'active'
        """,
        (int(user["id"]), name),
    )
    return int(user["id"])


def upsert_attendance_log(cursor: sqlite3.Cursor, employee_id: int, status: str, event_dt: datetime) -> None:
    work_date = event_dt.date().isoformat()
    time_value = event_dt.strftime("%H:%M:%S")
    event_type = determine_event_type(status)
    attendance_status = determine_attendance_status(status)

    cursor.execute(
        """
        INSERT INTO attendance_logs (
            employee_id,
            date,
            entry_time,
            exit_time,
            attendance_status,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(employee_id, date) DO UPDATE SET
            entry_time = CASE
                WHEN excluded.entry_time IS NOT NULL AND (
                    attendance_logs.entry_time IS NULL OR excluded.entry_time < attendance_logs.entry_time
                )
                THEN excluded.entry_time
                ELSE attendance_logs.entry_time
            END,
            exit_time = CASE
                WHEN excluded.exit_time IS NOT NULL AND (
                    attendance_logs.exit_time IS NULL OR excluded.exit_time > attendance_logs.exit_time
                )
                THEN excluded.exit_time
                ELSE attendance_logs.exit_time
            END,
            attendance_status = CASE
                WHEN attendance_logs.attendance_status = 'late' OR excluded.attendance_status = 'late' THEN 'late'
                WHEN attendance_logs.attendance_status = 'absent' THEN 'absent'
                ELSE excluded.attendance_status
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            employee_id,
            work_date,
            time_value if event_type == "CHECK-IN" else None,
            time_value if event_type == "CHECK-OUT" else None,
            attendance_status,
        ),
    )


def determine_event_type(status: str) -> str:
    if status.startswith("OVERTIME"):
        return "CHECK-OUT"
    if status.startswith("CHECK-OUT"):
        return "CHECK-OUT"
    return "CHECK-IN"


def determine_attendance_status(status: str) -> str:
    normalized = status.upper()
    if "LATE" in normalized or "WARNING" in normalized or "VIOLATION" in normalized:
        return "late"
    if "ABSENT" in normalized:
        return "absent"
    return "on_time"
