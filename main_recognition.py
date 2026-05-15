import cv2
import face_recognition
import json
import numpy as np
import os
from datetime import datetime, time
from liveness_utils import check_liveness, is_fake_texture
from database_utils import init_db, insert_user, load_registered_faces, load_todays_attendance_state, log_attendance_event

# -------------------------------
# SETTINGS & CONSTANTS
# -------------------------------
KNOWN_ENCODINGS, KNOWN_NAMES = load_registered_faces()
LIVENESS_STATUS = {}
LAST_EVENT = {}  # {name: {"type": "CHECK-IN"|"CHECK-OUT", "time": datetime}}
FRAME_COUNTER = 0
LOG_FILE = "attendance_logs.txt"

MIN_WORK_SECONDS = 2 * 60  # 2 min after CHECK-IN → next detection triggers CHECK-OUT
CHECKIN_COOLDOWN = 5 * 60   # 5 min after CHECK-OUT → next detection triggers new CHECK-IN

# -------------------------------
# TIME RULES
# -------------------------------
def get_status_by_time(event_type, current_dt):
    current_t = current_dt.time()
    morning_warning   = time(9, 15)
    morning_violation = time(9, 30)
    lunch_start       = time(12, 0)
    lunch_end         = time(13, 15)
    afternoon_warning   = time(13, 30)
    afternoon_violation = time(13, 45)
    overtime_threshold  = time(18, 0)

    if event_type == "CHECK-OUT":
        if current_t >= overtime_threshold:
            return "CHECK-OUT (After 18:00)"
        if lunch_start <= current_t <= lunch_end:
            return "CHECK-OUT (Lunch Break)"
        return "CHECK-OUT"

    # CHECK-IN time rules
    if lunch_start <= current_t <= lunch_end:
        return "CHECK-IN (Lunch Break)"
    if current_t > lunch_end:
        if current_t >= afternoon_violation:
            return "VIOLATION: Late (Afternoon)"
        if current_t >= afternoon_warning:
            return "WARNING: Late (Afternoon)"
        return "CHECK-IN"
    if current_t >= morning_violation:
        return "VIOLATION: Late (Morning)"
    if current_t >= morning_warning:
        return "WARNING: Late (Morning)"
    return "CHECK-IN"

# -------------------------------
# EVENT LOGIC
# -------------------------------
def should_log_event(name, current_time):
    """Return 'CHECK-IN', 'CHECK-OUT', or None based on last event."""
    last = LAST_EVENT.get(name)
    if last is None:
        return "CHECK-IN"
    elapsed = (current_time - last["time"]).total_seconds()
    if last["type"] == "CHECK-IN":
        return "CHECK-OUT" if elapsed >= MIN_WORK_SECONDS else None
    # last was CHECK-OUT
    return "CHECK-IN" if elapsed >= CHECKIN_COOLDOWN else None

# -------------------------------
# TXT LOGGING
# -------------------------------
def log_to_txt(name, status, dt):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{dt.strftime('%d/%m/%Y %H:%M:%S')} - {name} - {status}\n")

# -------------------------------
# UI HELPERS
# -------------------------------
def get_color(display_name):
    if "SPOOFING!" in display_name or "Unknown" in display_name:
        return (0, 0, 255)
    if "(Blink)" in display_name:
        return (0, 255, 255)
    return (0, 255, 0)

# -------------------------------
# MAIN LOOP
# -------------------------------
def run_recognition():
    global KNOWN_ENCODINGS, KNOWN_NAMES, FRAME_COUNTER

    video_capture = cv2.VideoCapture(0)
    current_face_results = []
    face_encodings = []

    print(f"System started. Logging to DB and {LOG_FILE}")
    print(f"Logic: CHECK-IN on first sight | CHECK-OUT after {MIN_WORK_SECONDS // 60} min | re-entry after {CHECKIN_COOLDOWN // 60} min cooldown")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        if FRAME_COUNTER % 2 == 0:
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            current_face_results = []

            for i, (face_loc, face_encoding) in enumerate(zip(face_locations, face_encodings)):
                top, right, bottom, left = face_loc
                top *= 4; right *= 4; bottom *= 4; left *= 4

                matches = face_recognition.compare_faces(KNOWN_ENCODINGS, face_encoding)
                display_name = "Unknown"

                if True in matches:
                    first_match_index = matches.index(True)
                    actual_name = KNOWN_NAMES[first_match_index]

                    ear, lap_var = check_liveness(frame, (top, right, bottom, left))

                    if i not in LIVENESS_STATUS:
                        LIVENESS_STATUS[i] = False

                    if is_fake_texture(lap_var, threshold=115):
                        display_name = "SPOOFING!"
                        LIVENESS_STATUS[i] = False
                    else:
                        if ear < 0.20:
                            LIVENESS_STATUS[i] = True

                        current_time = datetime.now()
                        event_type = should_log_event(actual_name, current_time)

                        if event_type == "CHECK-OUT":
                            # CHECK-OUT: face recognition alone is sufficient, no blink needed
                            display_name = actual_name
                            status = get_status_by_time("CHECK-OUT", current_time)
                            log_attendance_event(actual_name, status, current_time)
                            log_to_txt(actual_name, status, current_time)
                            LAST_EVENT[actual_name] = {"type": "CHECK-OUT", "time": current_time}
                            print(f"[CHECK-OUT] {actual_name} @ {current_time.strftime('%H:%M:%S')} — {status}")
                        elif event_type == "CHECK-IN" and LIVENESS_STATUS[i]:
                            # CHECK-IN: requires confirmed liveness (blink)
                            display_name = actual_name
                            status = get_status_by_time("CHECK-IN", current_time)
                            log_attendance_event(actual_name, status, current_time)
                            log_to_txt(actual_name, status, current_time)
                            LAST_EVENT[actual_name] = {"type": "CHECK-IN", "time": current_time}
                            print(f"[CHECK-IN] {actual_name} @ {current_time.strftime('%H:%M:%S')} — {status}")
                        elif event_type is None and LIVENESS_STATUS[i]:
                            display_name = actual_name
                        else:
                            display_name = f"{actual_name} (Blink)"

                current_face_results.append((top, right, bottom, left, display_name))

        FRAME_COUNTER += 1

        for (top, right, bottom, left, display_name) in current_face_results:
            color = get_color(display_name)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, display_name, (left + 6, bottom - 6),
                        cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow('Face Recognition System', frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('s') and len(face_encodings) > 0:
            name_input = input("Enter name for new record: ")
            if name_input:
                encoding_json = json.dumps(face_encodings[0].tolist())
                insert_user(name_input, encoding_json)
                KNOWN_ENCODINGS, KNOWN_NAMES = load_registered_faces()

        if key == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    init_db()
    LAST_EVENT.update(load_todays_attendance_state())
    if LAST_EVENT:
        state_summary = ", ".join(n + " (" + v["type"] + ")" for n, v in LAST_EVENT.items())
        print("Loaded today's state for: " + state_summary)
    run_recognition()
