from __future__ import annotations

from datetime import datetime

import numpy as np


def test_time_override_set_read_and_clear(isolated_paths):
    import time_override

    active = time_override.set_time_override("morning_warning")
    current = time_override.get_current_datetime()
    cleared = time_override.clear_time_override()

    assert active["active"] is True
    assert active["time"] == "09:16:00"
    assert current.hour == 9 and current.minute == 16
    assert cleared["active"] is False


def test_time_override_all_planned_scenarios_return_expected_times(isolated_paths):
    import time_override

    for scenario_key, scenario in time_override.SCENARIOS.items():
        active = time_override.set_time_override(scenario_key)
        current = time_override.get_current_datetime()

        assert active["active"] is True
        assert active["scenario_key"] == scenario_key
        assert active["time"] == scenario["time"]
        assert current.strftime("%H:%M:%S") == scenario["time"]


def test_time_override_rejects_unknown_scenario(isolated_paths):
    import pytest
    import time_override

    with pytest.raises(ValueError):
        time_override.set_time_override("not-a-scenario")


def test_time_override_handles_corrupt_file(isolated_paths):
    import time_override

    time_override.OVERRIDE_PATH.write_text("{bad json", encoding="utf-8")

    result = time_override.read_time_override()

    assert result["active"] is False
    assert result["label"] == "Real System Time"


def test_attendance_station_status_thresholds():
    import attendance_station

    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 8, 55)) == "CHECK-IN"
    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 9, 16)) == "WARNING: Late (Morning)"
    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 9, 31)) == "VIOLATION: Late (Morning)"
    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 12, 30)) == "CHECK-IN (Lunch Break)"
    assert attendance_station.get_status_by_time("CHECK-OUT", datetime(2026, 5, 30, 12, 30)) == "CHECK-OUT (Lunch Break)"
    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 13, 31)) == "WARNING: Late (Afternoon)"
    assert attendance_station.get_status_by_time("CHECK-IN", datetime(2026, 5, 30, 13, 46)) == "VIOLATION: Late (Afternoon)"
    assert attendance_station.get_status_by_time("CHECK-OUT", datetime(2026, 5, 30, 18, 1)) == "CHECK-OUT (After 18:00)"


def test_attendance_station_next_event_logic():
    import attendance_station

    station = attendance_station.AttendanceStation()
    start = datetime(2026, 5, 30, 9, 0)

    assert station._next_event_type("Ada", start) == "CHECK-IN"
    station.last_event["Ada"] = {"type": "CHECK-IN", "time": start}
    assert station._next_event_type("Ada", datetime(2026, 5, 30, 9, 0, 30)) is None
    assert station._next_event_type("Ada", datetime(2026, 5, 30, 9, 2)) == "CHECK-OUT"
    station.last_event["Ada"] = {"type": "CHECK-OUT", "time": start}
    assert station._next_event_type("Ada", datetime(2026, 5, 30, 9, 4)) is None
    assert station._next_event_type("Ada", datetime(2026, 5, 30, 9, 5)) == "CHECK-IN"


def test_calculate_ear_returns_low_value_for_blink_and_higher_for_open_eye():
    import liveness_utils

    open_eye = np.array(
        [[0, 0], [1, 2], [3, 2], [6, 0], [3, -2], [1, -2]],
        dtype=float,
    )
    blink_eye = np.array(
        [[0, 0], [1, 0.2], [3, 0.2], [6, 0], [3, -0.2], [1, -0.2]],
        dtype=float,
    )

    assert liveness_utils.calculate_ear(open_eye) > 0.6
    assert liveness_utils.calculate_ear(blink_eye) < 0.1


def test_is_fake_texture_flags_low_laplacian_variance():
    import liveness_utils

    assert liveness_utils.is_fake_texture(20, threshold=110) is True
    assert liveness_utils.is_fake_texture(250, threshold=110) is False
