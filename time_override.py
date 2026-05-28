from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
OVERRIDE_PATH = PROJECT_ROOT / ".test_time_override.json"

SCENARIOS: dict[str, dict[str, str]] = {
    "morning_on_time": {"label": "Morning On-Time", "time": "08:55:00"},
    "morning_warning": {"label": "Morning Warning", "time": "09:16:00"},
    "morning_violation": {"label": "Morning Violation", "time": "09:31:00"},
    "lunch_break": {"label": "Lunch Break", "time": "12:30:00"},
    "afternoon_warning": {"label": "Afternoon Warning", "time": "13:31:00"},
    "afternoon_violation": {"label": "Afternoon Violation", "time": "13:46:00"},
    "overtime": {"label": "Overtime", "time": "18:05:00"},
}


def get_current_datetime() -> datetime:
    override = read_time_override()
    if not override["active"]:
        return datetime.now()

    try:
        override_time = time.fromisoformat(override["time"])
    except ValueError:
        return datetime.now()

    now = datetime.now()
    return datetime.combine(now.date(), override_time)


def read_time_override() -> dict[str, Any]:
    if not OVERRIDE_PATH.exists():
        return {
            "active": False,
            "label": "Real System Time",
            "time": None,
            "current_datetime": datetime.now().isoformat(),
            "scenarios": build_scenarios(),
        }

    try:
        payload = json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}

    active = bool(payload.get("active"))
    scenario_key = str(payload.get("scenario_key", "custom"))
    time_value = str(payload.get("time", ""))
    label = str(payload.get("label") or SCENARIOS.get(scenario_key, {}).get("label") or "Custom Test Time")

    current_dt = datetime.now()
    if active:
        try:
            current_dt = datetime.combine(current_dt.date(), time.fromisoformat(time_value))
        except ValueError:
            active = False
            time_value = ""
            label = "Real System Time"

    return {
        "active": active,
        "scenario_key": scenario_key if active else None,
        "label": label if active else "Real System Time",
        "time": time_value if active else None,
        "current_datetime": current_dt.isoformat(),
        "scenarios": build_scenarios(),
    }


def set_time_override(scenario_key: str) -> dict[str, Any]:
    scenario = SCENARIOS.get(scenario_key)
    if scenario is None:
        raise ValueError("Unknown presentation time scenario.")

    payload = {
        "active": True,
        "scenario_key": scenario_key,
        "label": scenario["label"],
        "time": scenario["time"],
        "updated_at": datetime.now().isoformat(),
    }
    OVERRIDE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return read_time_override()


def clear_time_override() -> dict[str, Any]:
    if OVERRIDE_PATH.exists():
        OVERRIDE_PATH.unlink()
    return read_time_override()


def build_scenarios() -> list[dict[str, str]]:
    return [
        {"key": key, "label": value["label"], "time": value["time"]}
        for key, value in SCENARIOS.items()
    ]
