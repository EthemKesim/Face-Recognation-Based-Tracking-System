from __future__ import annotations

import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from time_override import get_current_datetime


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "face_records.db"
LOG_PATH = PROJECT_ROOT / "attendance_logs.txt"
LOG_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"

ATTENDANCE_RULE_DEFAULTS: dict[str, str] = {
    "work_start": "09:00",
    "late_warning": "09:15",
    "late_violation": "09:30",
    "lunch_start": "12:00",
    "lunch_end": "13:15",
    "afternoon_warning": "13:30",
    "afternoon_violation": "13:45",
    "work_end": "18:00",
}

PASSWORD_HASH_ITERATIONS = 260_000


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
                photo_path TEXT,
                department_role TEXT
            )
            """
        )
        ensure_employee_optional_columns(cursor)
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS unknown_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                image_path TEXT,
                detection_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                admin_username TEXT NOT NULL,
                action_type TEXT NOT NULL,
                details TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_admin_log_timestamp
            ON admin_activity_log(timestamp)
            """
        )

        migrate_users_to_employees(cursor)
        migrate_text_logs_to_attendance(cursor)
        connection.commit()


def hash_admin_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_admin_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, AttributeError):
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def ensure_admin_account(username: str, password: str) -> bool:
    username = username.strip()
    if not username or not password:
        return False

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM admins WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            return False

        cursor.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, hash_admin_password(password)),
        )
        connection.commit()
        return True


def create_admin_account(username: str, password: str) -> dict[str, Any]:
    username = username.strip()
    if not username:
        return {"success": False, "error": "Admin username is required."}
    if len(password) < 6:
        return {"success": False, "error": "Admin password must be at least 6 characters."}

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (username, hash_admin_password(password)),
            )
            admin_id = int(cursor.lastrowid)
            connection.commit()
    except sqlite3.IntegrityError:
        return {"success": False, "error": "An admin with this username already exists."}

    return {"success": True, "admin": {"id": admin_id, "username": username}}


def verify_admin_credentials(username: str, password: str) -> bool:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT password_hash FROM admins WHERE username = ?", (username.strip(),))
        row = cursor.fetchone()

    if row is None:
        return False

    return verify_admin_password(password, row["password_hash"])


def read_admin_accounts() -> list[dict[str, Any]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, username FROM admins ORDER BY username COLLATE NOCASE")
        rows = cursor.fetchall()

    return [{"id": row["id"], "username": row["username"]} for row in rows]


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


def ensure_employee_optional_columns(cursor: sqlite3.Cursor) -> None:
    cursor.execute("PRAGMA table_info(employees)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "department_role" not in columns:
        cursor.execute("ALTER TABLE employees ADD COLUMN department_role TEXT")

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


def load_todays_attendance_state() -> dict[str, dict]:
    """Return {employee_name: {"type": "CHECK-IN"|"CHECK-OUT", "time": datetime}} for today's records."""
    today = get_current_datetime().date().isoformat()
    state: dict[str, dict] = {}

    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT e.full_name, a.entry_time, a.exit_time
            FROM attendance_logs a
            JOIN employees e ON e.id = a.employee_id
            WHERE a.date = ?
            """,
            (today,),
        )
        rows = cursor.fetchall()

    for row in rows:
        name = row["full_name"]
        entry = row["entry_time"]
        exit_ = row["exit_time"]

        if exit_:
            try:
                t = datetime.strptime(f"{today} {exit_}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                t = get_current_datetime()
            state[name] = {"type": "CHECK-OUT", "time": t}
        elif entry:
            try:
                t = datetime.strptime(f"{today} {entry}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                t = get_current_datetime()
            state[name] = {"type": "CHECK-IN", "time": t}

    return state


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


def insert_user(
    name: str,
    face_vector_json: str,
    photo_path: str | None = None,
    department_role: str | None = None,
) -> int:
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
        cursor.execute(
            """
            UPDATE employees
            SET department_role = ?
            WHERE id = ?
            """,
            (department_role, user_id),
        )
        connection.commit()
        return user_id


def fetch_registered_users() -> list[sqlite3.Row]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, name FROM users ORDER BY id")
        return cursor.fetchall()


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
        cursor.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
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


def update_employee_photo(user_id: int, photo_path: str) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE employees SET photo_path = ? WHERE id = ?", (photo_path, user_id))
        connection.commit()


def employee_name_exists(name: str) -> str | None:
    """Return the stored name if a case-insensitive match already exists, else None."""
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT full_name FROM employees WHERE lower(full_name) = lower(?) LIMIT 1",
            (name,),
        )
        row = cursor.fetchone()
        return row["full_name"] if row else None


def log_manual_event(user_id: int, event_type: str) -> dict[str, Any]:
    if event_type not in ("CHECK-IN", "CHECK-OUT"):
        return {"success": False, "error": "Invalid event type."}

    with get_connection() as connection:
        cursor = connection.cursor()
        employee = get_employee(cursor, user_id)
        if employee is None:
            return {"success": False, "error": "Employee not found."}

        now = get_current_datetime()
        status = f"{event_type} (Manual)"
        upsert_attendance_log(cursor, user_id, status, now)
        connection.commit()

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{now.strftime(LOG_DATETIME_FORMAT)} - {employee['full_name']} - {status}\n")

    return {
        "success": True,
        "employee_id": user_id,
        "employee_name": employee["full_name"],
        "event_type": event_type,
        "timestamp": now.isoformat(),
    }


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


# ---------------------------------------------------------------------------
# Employee edit
# ---------------------------------------------------------------------------

def update_employee_data(
    user_id: int,
    full_name: str | None = None,
    department_role: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM employees WHERE id = ?", (user_id,))
        if cursor.fetchone() is None:
            return {"success": False, "error": "Employee not found."}

        if full_name is not None:
            cursor.execute("UPDATE employees SET full_name = ? WHERE id = ?", (full_name, user_id))
            cursor.execute("UPDATE users SET name = ? WHERE id = ?", (full_name, user_id))
        if department_role is not None:
            cursor.execute("UPDATE employees SET department_role = ? WHERE id = ?", (department_role, user_id))
        if status in ("active", "inactive"):
            cursor.execute("UPDATE employees SET status = ? WHERE id = ?", (status, user_id))
        connection.commit()

    return {"success": True, "employee_id": user_id}


# ---------------------------------------------------------------------------
# Unknown faces
# ---------------------------------------------------------------------------

def record_unknown_face(image_path: str | None = None) -> int:
    now = get_current_datetime()
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, image_path, last_seen FROM unknown_faces ORDER BY last_seen DESC LIMIT 1"
        )
        recent = cursor.fetchone()

        if recent:
            try:
                last_seen_dt = datetime.fromisoformat(recent["last_seen"])
            except (ValueError, TypeError):
                last_seen_dt = None

            if last_seen_dt and (now - last_seen_dt).total_seconds() < 300:
                cursor.execute(
                    """
                    UPDATE unknown_faces
                    SET last_seen = ?,
                        detection_count = detection_count + 1,
                        image_path = COALESCE(image_path, ?)
                    WHERE id = ?
                    """,
                    (now.isoformat(), image_path, recent["id"]),
                )
                connection.commit()
                return int(recent["id"])

        cursor.execute(
            """
            INSERT INTO unknown_faces (first_seen, last_seen, image_path, detection_count)
            VALUES (?, ?, ?, 1)
            """,
            (now.isoformat(), now.isoformat(), image_path),
        )
        connection.commit()
        return int(cursor.lastrowid)


def load_unknown_faces() -> list[dict[str, Any]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, first_seen, last_seen, image_path, detection_count
            FROM unknown_faces
            ORDER BY last_seen DESC
            """
        )
        rows = cursor.fetchall()

    result = []
    for row in rows:
        img_path = row["image_path"]
        image_url = ("/" + img_path.replace("\\", "/").lstrip("/")) if img_path else None
        result.append(
            {
                "id": row["id"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "image_path": img_path,
                "image_url": image_url,
                "detection_count": row["detection_count"],
            }
        )
    return result


def delete_unknown_face(face_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, image_path FROM unknown_faces WHERE id = ?", (face_id,))
        row = cursor.fetchone()
        if row is None:
            return {"deleted": False, "error": "Record not found."}

        image_path = row["image_path"]
        cursor.execute("DELETE FROM unknown_faces WHERE id = ?", (face_id,))
        connection.commit()

    if image_path:
        candidate = resolve_managed_file_path(image_path)
        if candidate and candidate.exists() and candidate.is_file():
            try:
                candidate.unlink()
            except OSError:
                pass

    return {"deleted": True, "face_id": face_id}


def get_unknown_face(face_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, first_seen, last_seen, image_path, detection_count FROM unknown_faces WHERE id = ?",
            (face_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    img_path = row["image_path"]
    return {
        "id": row["id"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "image_path": img_path,
        "image_url": ("/" + img_path.replace("\\", "/").lstrip("/")) if img_path else None,
        "detection_count": row["detection_count"],
    }


# ---------------------------------------------------------------------------
# Attendance rules (stored in settings table)
# ---------------------------------------------------------------------------

def get_attendance_rules() -> dict[str, str]:
    rules = dict(ATTENDANCE_RULE_DEFAULTS)
    with get_connection() as connection:
        cursor = connection.cursor()
        for key in rules:
            cursor.execute("SELECT value FROM settings WHERE key = ?", (f"rule_{key}",))
            row = cursor.fetchone()
            if row and row["value"]:
                rules[key] = row["value"]
    return rules


def update_attendance_rules(rules: dict[str, str]) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        for key, value in rules.items():
            if key in ATTENDANCE_RULE_DEFAULTS:
                cursor.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (f"rule_{key}", value),
                )
        connection.commit()


# ---------------------------------------------------------------------------
# Admin activity log
# ---------------------------------------------------------------------------

def write_admin_log(admin_username: str, action_type: str, details: str | None = None) -> None:
    now = get_current_datetime()
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO admin_activity_log (timestamp, admin_username, action_type, details)
            VALUES (?, ?, ?, ?)
            """,
            (now.isoformat(), admin_username, action_type, details),
        )
        connection.commit()


def read_admin_logs(limit: int = 200) -> list[dict[str, Any]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, admin_username, action_type, details
            FROM admin_activity_log
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "admin_username": row["admin_username"],
            "action_type": row["action_type"],
            "details": row["details"],
        }
        for row in rows
    ]
