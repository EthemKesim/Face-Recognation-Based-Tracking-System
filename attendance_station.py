from __future__ import annotations

import threading
import time as sleep_time
from datetime import datetime, time
from pathlib import Path
from typing import Any

import cv2
import face_recognition

from database_utils import (
    LOG_DATETIME_FORMAT,
    LOG_PATH,
    PROJECT_ROOT,
    init_db,
    load_registered_faces,
    load_todays_attendance_state,
    log_attendance_event,
    record_unknown_face,
)
from liveness_utils import check_liveness, is_fake_texture
from time_override import get_current_datetime, read_time_override


MIN_WORK_SECONDS = 2 * 60
CHECKIN_COOLDOWN_SECONDS = 5 * 60
FACE_RELOAD_SECONDS = 10
FRAME_SCALE = 0.25


def get_status_by_time(event_type: str, current_dt: datetime) -> str:
    current_time = current_dt.time()
    morning_warning = time(9, 15)
    morning_violation = time(9, 30)
    lunch_start = time(12, 0)
    lunch_end = time(13, 15)
    afternoon_warning = time(13, 30)
    afternoon_violation = time(13, 45)
    overtime_threshold = time(18, 0)

    if event_type == "CHECK-OUT":
        if current_time >= overtime_threshold:
            return "CHECK-OUT (After 18:00)"
        if lunch_start <= current_time <= lunch_end:
            return "CHECK-OUT (Lunch Break)"
        return "CHECK-OUT"

    if lunch_start <= current_time <= lunch_end:
        return "CHECK-IN (Lunch Break)"
    if current_time > lunch_end:
        if current_time >= afternoon_violation:
            return "VIOLATION: Late (Afternoon)"
        if current_time >= afternoon_warning:
            return "WARNING: Late (Afternoon)"
        return "CHECK-IN"
    if current_time >= morning_violation:
        return "VIOLATION: Late (Morning)"
    if current_time >= morning_warning:
        return "WARNING: Late (Morning)"
    return "CHECK-IN"


def display_color(label: str) -> tuple[int, int, int]:
    if "SPOOFING" in label or label == "Unknown":
        return (32, 70, 235)
    if "Blink" in label:
        return (35, 202, 245)
    return (62, 188, 92)


class AttendanceStation:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self.lock = threading.Condition()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.frame_version = 0
        self.latest_jpeg: bytes | None = None
        self.latest_frame_at: str | None = None
        self.latest_recognition: dict[str, Any] | None = None
        self.last_unknown_at: datetime | None = None
        self.last_error: str | None = None
        self.online = False
        self.current_day = get_current_datetime().date()
        self.last_event: dict[str, dict[str, Any]] = {}
        self.blinked_faces: dict[str, bool] = {}
        self.known_encodings: list[Any] = []
        self.known_names: list[str] = []
        self.last_face_reload = 0.0

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        self.stop_event.clear()
        self.worker = threading.Thread(target=self._run, name="attendance-station", daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.lock:
            self.lock.notify_all()

    def status(self) -> dict[str, Any]:
        with self.lock:
            worker_running = bool(self.worker and self.worker.is_alive())
            return {
                "camera_index": self.camera_index,
                "online": self.online,
                "worker_running": worker_running,
                "last_frame_at": self.latest_frame_at,
                "last_error": self.last_error,
                "known_faces": len(self.known_names),
                "latest_recognition": self.latest_recognition,
                "test_time": read_time_override(),
                "logic": {
                    "check_out_after_seconds": MIN_WORK_SECONDS,
                    "reentry_after_seconds": CHECKIN_COOLDOWN_SECONDS,
                    "checkin_liveness": "blink required",
                },
            }

    def wait_for_frame(self, last_version: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self.lock:
            if self.frame_version == last_version and not self.stop_event.is_set():
                self.lock.wait(timeout=timeout)
            return self.frame_version, self.latest_jpeg

    def _run(self) -> None:
        init_db()
        self._load_day_state()
        self._reload_faces()
        capture = cv2.VideoCapture(self.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        frame_counter = 0
        rendered_faces: list[tuple[int, int, int, int, str]] = []

        if not capture.isOpened():
            self._set_error(f"Camera {self.camera_index} could not be opened.")
            capture.release()
            return

        with self.lock:
            self.online = True
            self.last_error = None

        try:
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    self._set_error("Camera frame could not be read.")
                    sleep_time.sleep(0.25)
                    continue

                self._roll_day_if_needed()
                self._reload_faces_if_due()

                if frame_counter % 2 == 0:
                    rendered_faces = self._recognize_faces(frame)
                frame_counter += 1

                for top, right, bottom, left, label in rendered_faces:
                    color = display_color(label)
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.rectangle(frame, (left, max(top, bottom - 34)), (right, bottom), color, cv2.FILLED)
                    cv2.putText(
                        frame,
                        label,
                        (left + 6, max(top + 21, bottom - 10)),
                        cv2.FONT_HERSHEY_DUPLEX,
                        0.58,
                        (255, 255, 255),
                        1,
                    )

                cv2.putText(
                    frame,
                    "Attendance Station",
                    (18, 36),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.86,
                    (255, 255, 255),
                    2,
                )
                self._publish_frame(frame)
        except Exception as exc:
            self._set_error(f"Station stopped: {exc}")
        finally:
            capture.release()
            with self.lock:
                self.online = False
                self.lock.notify_all()

    def _recognize_faces(self, frame) -> list[tuple[int, int, int, int, str]]:
        small_frame = cv2.resize(frame, (0, 0), fx=FRAME_SCALE, fy=FRAME_SCALE)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_small_frame)
        encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
        results: list[tuple[int, int, int, int, str]] = []

        for location, encoding in zip(face_locations, encodings):
            top, right, bottom, left = [int(value / FRAME_SCALE) for value in location]
            label = "Unknown"
            name = self._match_name(encoding)

            if name:
                label = self._handle_known_face(name, frame, (top, right, bottom, left))
            else:
                self._record_unknown_detection(frame, (top, right, bottom, left))

            results.append((top, right, bottom, left, label))

        return results

    def _match_name(self, encoding) -> str | None:
        if not self.known_encodings:
            return None

        distances = face_recognition.face_distance(self.known_encodings, encoding)
        best_index = int(distances.argmin())
        return self.known_names[best_index] if float(distances[best_index]) < 0.6 else None

    def _handle_known_face(self, name: str, frame, location: tuple[int, int, int, int]) -> str:
        try:
            ear, laplacian_var = check_liveness(frame, location)
        except Exception as exc:
            self._set_error(f"Liveness check failed: {exc}")
            return f"{name} (Liveness error)"

        if is_fake_texture(laplacian_var, threshold=115):
            self.blinked_faces[name] = False
            return "SPOOFING!"

        if ear < 0.20:
            self.blinked_faces[name] = True

        now = get_current_datetime()
        event_type = self._next_event_type(name, now)
        has_blinked = self.blinked_faces.get(name, False)

        if event_type == "CHECK-OUT":
            return self._record_event(name, event_type, now)
        if event_type == "CHECK-IN" and has_blinked:
            return self._record_event(name, event_type, now)
        if event_type is None and has_blinked:
            return name
        return f"{name} (Blink)"

    def _next_event_type(self, name: str, now: datetime) -> str | None:
        previous = self.last_event.get(name)
        if previous is None:
            return "CHECK-IN"

        elapsed = (now - previous["time"]).total_seconds()
        if previous["type"] == "CHECK-IN":
            return "CHECK-OUT" if elapsed >= MIN_WORK_SECONDS else None
        return "CHECK-IN" if elapsed >= CHECKIN_COOLDOWN_SECONDS else None

    def _record_event(self, name: str, event_type: str, event_time: datetime) -> str:
        status = get_status_by_time(event_type, event_time)
        employee_id = log_attendance_event(name, status, event_time)
        if employee_id is None:
            return name

        with Path(LOG_PATH).open("a", encoding="utf-8") as log_file:
            log_file.write(f"{event_time.strftime(LOG_DATETIME_FORMAT)} - {name} - {status}\n")

        self.last_event[name] = {"type": event_type, "time": event_time}
        self.blinked_faces[name] = False
        with self.lock:
            self.latest_recognition = {
                "recognition_status": "Recognized",
                "employee_name": name,
                "event_type": event_type,
                "status": status,
                "timestamp": event_time.isoformat(),
            }
            self.lock.notify_all()
        return name

    def _record_unknown_detection(self, frame=None, location=None) -> None:
        now = get_current_datetime()
        if self.last_unknown_at and (now - self.last_unknown_at).total_seconds() < 3:
            return

        self.last_unknown_at = now

        image_path: str | None = None
        if frame is not None:
            try:
                images_dir = PROJECT_ROOT / "unknown_face_images"
                images_dir.mkdir(exist_ok=True)
                filename = f"unknown_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                full_path = images_dir / filename
                if location is not None:
                    top, right, bottom, left = location
                    h, w = frame.shape[:2]
                    pad = 40
                    crop = frame[max(0, top - pad):min(h, bottom + pad), max(0, left - pad):min(w, right + pad)]
                    cv2.imwrite(str(full_path), crop if crop.size > 0 else frame)
                else:
                    cv2.imwrite(str(full_path), frame)
                image_path = f"unknown_face_images/{filename}"
            except Exception:
                pass

        try:
            record_unknown_face(image_path)
        except Exception:
            pass

        with self.lock:
            self.latest_recognition = {
                "recognition_status": "Unknown",
                "employee_name": None,
                "event_type": "UNKNOWN",
                "status": "Unknown face detected",
                "timestamp": now.isoformat(),
                "registration_suggested": True,
                "image_url": (f"/{image_path}" if image_path else None),
            }
            self.lock.notify_all()

    def _publish_frame(self, frame) -> None:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if not ok:
            return

        with self.lock:
            self.latest_jpeg = encoded.tobytes()
            self.latest_frame_at = get_current_datetime().isoformat()
            self.frame_version += 1
            self.lock.notify_all()

    def _reload_faces_if_due(self) -> None:
        if sleep_time.monotonic() - self.last_face_reload >= FACE_RELOAD_SECONDS:
            self._reload_faces()

    def _reload_faces(self) -> None:
        self.known_encodings, self.known_names = load_registered_faces()
        self.last_face_reload = sleep_time.monotonic()

    def _roll_day_if_needed(self) -> None:
        current_day = get_current_datetime().date()
        if self.current_day != current_day:
            self.current_day = current_day
            self._load_day_state()
            self.blinked_faces.clear()

    def _load_day_state(self) -> None:
        self.last_event = load_todays_attendance_state()

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.last_error = message
            self.lock.notify_all()
