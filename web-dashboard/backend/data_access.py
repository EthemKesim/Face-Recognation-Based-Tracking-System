from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_SOURCE_DIR = Path(__file__).resolve().parents[2] / "Face-Recognation-Based-Tracking-System-main"
DB_PATH = PROJECT_SOURCE_DIR / "face_records.db"
LOG_PATH = PROJECT_SOURCE_DIR / "attendance_logs.txt"
MAIN_SCRIPT_PATH = PROJECT_SOURCE_DIR / "main_recognition.py"

LOG_PATTERN = re.compile(r"^(?P<timestamp>\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}) - (?P<name>.+?) - (?P<status>.+)$")
LOG_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"
API_DATE_FORMAT = "%Y-%m-%d"


@dataclass
class AttendanceRecord:
    employee_id: int | None
    employee_name: str
    work_date: str
    entry_time: str | None
    exit_time: str | None
    current_status: str
    last_event_type: str
    notes: list[str]
    events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "date": self.work_date,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "current_status": self.current_status,
            "event_type": self.last_event_type,
            "notes": self.notes,
            "events": self.events,
        }


def load_registered_users() -> list[dict[str, Any]]:
    # Database parsing happens here. The dashboard reads the existing SQLite
    # `users` table directly and never writes back to the recognition project.
    if not DB_PATH.exists():
        return []

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE, id")
        rows = cursor.fetchall()

    return [{"id": row[0], "name": row[1], "face_registered": True} for row in rows]


def parse_log_events() -> list[dict[str, Any]]:
    # Log parsing happens here. Each line is interpreted from the current
    # `attendance_logs.txt` format produced by the Python recognition script.
    if not LOG_PATH.exists():
        return []

    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(LOG_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            events.append(
                {
                    "id": f"log-{line_number}",
                    "line_number": line_number,
                    "raw": line,
                    "timestamp": None,
                    "date": None,
                    "time": None,
                    "employee_name": None,
                    "status": "UNPARSED",
                    "event_type": "UNKNOWN",
                    "status_group": "unknown",
                    "notes": ["This line could not be parsed by the dashboard."],
                }
            )
            continue

        timestamp = datetime.strptime(match.group("timestamp"), LOG_DATETIME_FORMAT)
        name = match.group("name").strip()
        status = match.group("status").strip()

        events.append(
            {
                "id": f"log-{line_number}",
                "line_number": line_number,
                "raw": line,
                "timestamp": timestamp.isoformat(),
                "date": timestamp.strftime(API_DATE_FORMAT),
                "time": timestamp.strftime("%H:%M:%S"),
                "employee_name": name,
                "status": status,
                "event_type": determine_event_type(status),
                "status_group": determine_status_group(status),
                "notes": build_notes(status),
                "_dt": timestamp,
            }
        )

    events.sort(key=lambda event: event.get("_dt") or datetime.min, reverse=True)
    return events


def determine_event_type(status: str) -> str:
    if status.startswith("OVERTIME"):
        return "CHECK-OUT"
    if status.startswith("CHECK-IN") or status.startswith("WARNING: Late") or status.startswith("VIOLATION: Late"):
        return "CHECK-IN"
    if status.startswith("CHECK-OUT"):
        return "CHECK-OUT"
    return "UNKNOWN"


def determine_status_group(status: str) -> str:
    normalized = status.upper()
    if "VIOLATION" in normalized or "WARNING" in normalized or "LATE" in normalized:
        return "late"
    if "LUNCH BREAK" in normalized:
        return "lunch"
    if "OVERTIME" in normalized:
        return "overtime"
    if normalized.startswith("CHECK-OUT"):
        return "checkout"
    if normalized.startswith("CHECK-IN"):
        return "checkin"
    return "neutral"


def build_notes(status: str) -> list[str]:
    notes: list[str] = []
    if "Lunch Break" in status:
        notes.append("Lunch break window")
    if "WARNING: Late" in status:
        notes.append("Late warning")
    if "VIOLATION: Late" in status:
        notes.append("Late violation")
    if "OVERTIME" in status:
        notes.append("Overtime detected")
    if "After 18:00" in status:
        notes.append("Checked out after overtime threshold")
    return notes


def build_attendance_records(
    events: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> list[AttendanceRecord]:
    user_map = {user["name"]: user["id"] for user in users}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        if not event.get("employee_name") or not event.get("date"):
            continue
        grouped[(event["employee_name"], event["date"])].append(event)

    records: list[AttendanceRecord] = []
    for (employee_name, work_date), employee_events in grouped.items():
        ordered_events = sorted(employee_events, key=lambda item: item["_dt"])
        entry_time = next(
            (event["time"] for event in ordered_events if event["event_type"] == "CHECK-IN"),
            None,
        )
        exit_time = next(
            (event["time"] for event in reversed(ordered_events) if event["event_type"] == "CHECK-OUT"),
            None,
        )
        last_event = ordered_events[-1]
        current_status = derive_current_status(ordered_events)

        records.append(
            AttendanceRecord(
                employee_id=user_map.get(employee_name),
                employee_name=employee_name,
                work_date=work_date,
                entry_time=entry_time,
                exit_time=exit_time,
                current_status=current_status,
                last_event_type=last_event["event_type"],
                notes=collect_record_notes(ordered_events, current_status),
                events=[serialize_event(event) for event in reversed(ordered_events)],
            )
        )

    records.sort(key=lambda record: (record.work_date, record.employee_name), reverse=True)
    return records


def serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "timestamp": event["timestamp"],
        "date": event["date"],
        "time": event["time"],
        "employee_name": event["employee_name"],
        "status": event["status"],
        "event_type": event["event_type"],
        "status_group": event["status_group"],
        "notes": event["notes"],
        "raw": event["raw"],
    }


def derive_current_status(events: list[dict[str, Any]]) -> str:
    last_event = events[-1]
    status = last_event["status"]
    if last_event["event_type"] == "CHECK-IN":
        if "Lunch Break" in status:
            return "Lunch Break"
        return "Still Inside"
    if last_event["event_type"] == "CHECK-OUT":
        if "OVERTIME" in status:
            return "Checked Out (Overtime)"
        return "Checked Out"
    return status


def collect_record_notes(events: list[dict[str, Any]], current_status: str) -> list[str]:
    notes: list[str] = []
    if current_status == "Still Inside":
        notes.append("No check-out event recorded yet for this day.")
    if any("WARNING: Late" in event["status"] for event in events):
        notes.append("Includes a late warning event.")
    if any("VIOLATION: Late" in event["status"] for event in events):
        notes.append("Includes a late violation event.")
    if any("Lunch Break" in event["status"] for event in events):
        notes.append("Contains a lunch break state.")
    if any("OVERTIME" in event["status"] for event in events):
        notes.append("Contains overtime.")
    return notes


def get_dashboard_data() -> dict[str, Any]:
    users = load_registered_users()
    events = parse_log_events()
    records = build_attendance_records(events, users)
    today = date.today().strftime(API_DATE_FORMAT)
    todays_records = [record for record in records if record.work_date == today]
    latest_detection = serialize_event(events[0]) if events else None

    return {
        "users": users,
        "events": [serialize_event(event) for event in events],
        "records": [record.to_dict() for record in records],
        "today_records": [record.to_dict() for record in todays_records],
        "latest_detection": latest_detection,
        "summary": build_summary(users, todays_records, events),
    }


def build_summary(
    users: list[dict[str, Any]],
    todays_records: list[AttendanceRecord],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    present_today = [record for record in todays_records if record.entry_time]
    late_today = [
        record
        for record in todays_records
        if any("Late" in event["status"] for event in record.events)
    ]
    checked_out_today = [record for record in todays_records if record.exit_time]
    overtime_today = [
        record
        for record in todays_records
        if any("OVERTIME" in event["status"] for event in record.events)
    ]

    return {
        "total_registered_employees": len(users),
        "present_today": len(present_today),
        "late_today": len(late_today),
        "checked_out_today": len(checked_out_today),
        "overtime_employees": len(overtime_today),
        "recent_detections": [serialize_event(event) for event in events[:8]],
    }


def filter_events(
    events: list[dict[str, Any]],
    name_query: str | None = None,
    work_date: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    filtered = []
    name_query_normalized = (name_query or "").strip().lower()
    status_filter_normalized = (status_filter or "").strip().lower()

    for event in events:
        if name_query_normalized and name_query_normalized not in (event.get("employee_name") or "").lower():
            continue
        if work_date and event.get("date") != work_date:
            continue
        if status_filter_normalized:
            haystack = f'{event.get("status", "")} {event.get("status_group", "")} {event.get("event_type", "")}'.lower()
            if status_filter_normalized not in haystack:
                continue
        filtered.append(serialize_event(event))

    return filtered


def filter_records(
    records: list[dict[str, Any]],
    name_query: str | None = None,
    work_date: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    filtered = []
    name_query_normalized = (name_query or "").strip().lower()
    status_filter_normalized = (status_filter or "").strip().lower()

    for record in records:
        if name_query_normalized and name_query_normalized not in record["employee_name"].lower():
            continue
        if work_date and record["date"] != work_date:
            continue
        if status_filter_normalized:
            record_haystack = " ".join(
                [record["current_status"], record["event_type"], " ".join(record["notes"])]
            ).lower()
            if status_filter_normalized not in record_haystack:
                continue
        filtered.append(record)

    return filtered


def build_employee_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    users = data["users"]
    events = data["events"]
    records = data["records"]
    latest_event_by_name: dict[str, dict[str, Any]] = {}
    todays_record_by_name: dict[str, dict[str, Any]] = {}
    today = date.today().strftime(API_DATE_FORMAT)

    for event in events:
        name = event.get("employee_name")
        if name and name not in latest_event_by_name:
            latest_event_by_name[name] = event

    for record in records:
        if record["date"] == today and record["employee_name"] not in todays_record_by_name:
            todays_record_by_name[record["employee_name"]] = record

    rows = []
    for user in users:
        latest_event = latest_event_by_name.get(user["name"])
        today_record = todays_record_by_name.get(user["name"])
        rows.append(
            {
                "id": user["id"],
                "name": user["name"],
                "face_registered": user["face_registered"],
                "last_seen": latest_event["timestamp"] if latest_event else None,
                "current_status": today_record["current_status"] if today_record else "Absent / No activity today",
                "today_record": today_record,
            }
        )

    return rows


def get_employee_detail(employee_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    employee = next((user for user in data["users"] if user["id"] == employee_id), None)
    if not employee:
        return None

    employee_records = [record for record in data["records"] if record["employee_id"] == employee_id]
    employee_events = [event for event in data["events"] if event.get("employee_name") == employee["name"]]
    latest_event = employee_events[0] if employee_events else None

    late_count = sum(
        1 for event in employee_events if "WARNING: Late" in event["status"] or "VIOLATION: Late" in event["status"]
    )
    overtime_count = sum(1 for event in employee_events if "OVERTIME" in event["status"])

    return {
        "id": employee["id"],
        "name": employee["name"],
        "face_registered": employee["face_registered"],
        "latest_attendance_state": employee_records[0]["current_status"] if employee_records else "No attendance records",
        "latest_event": latest_event,
        "history": employee_records,
        "late_history_count": late_count,
        "overtime_history_count": overtime_count,
    }


def get_status_rules() -> dict[str, Any]:
    return {
        "source": str(MAIN_SCRIPT_PATH),
        "database_path": str(DB_PATH),
        "log_path": str(LOG_PATH),
        "rules": [
            {"name": "Morning Warning", "time": "09:15", "description": "CHECK-IN after 09:15 becomes WARNING: Late (Morning)."},
            {"name": "Morning Violation", "time": "09:30", "description": "CHECK-IN after 09:30 becomes VIOLATION: Late (Morning)."},
            {"name": "Lunch Break Window", "time": "12:00 - 13:15", "description": "Any check-in or check-out inside this range includes the Lunch Break label."},
            {"name": "Afternoon Warning", "time": "13:30", "description": "Post-lunch CHECK-IN after 13:30 becomes WARNING: Late (Afternoon)."},
            {"name": "Afternoon Violation", "time": "13:45", "description": "Post-lunch CHECK-IN after 13:45 becomes VIOLATION: Late (Afternoon)."},
            {"name": "Overtime Threshold", "time": "18:00", "description": "CHECK-OUT after 18:00 is labeled CHECK-OUT (After 18:00)."},
            {"name": "Work Duration Overtime", "time": "9 hours worked", "description": "If time between check-in and check-out exceeds 9 hours, the system writes OVERTIME: <hours>."},
        ],
    }


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
