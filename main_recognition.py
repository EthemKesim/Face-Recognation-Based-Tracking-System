import cv2
import face_recognition
import sqlite3
import numpy as np
import json
import random
from datetime import datetime, time

def load_registered_faces():
    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, face_vector FROM users")
    rows = cursor.fetchall()

    known_encodings = []
    known_names = []

    for row in rows:
        known_names.append(row[0])
        known_encodings.append(np.array(json.loads(row[1])))

    conn.close()
    return known_encodings, known_names


def get_status_by_time(event_type, current_dt):
    current_t = current_dt.time()

    # Time rules
    morning_warning = time(9, 15)
    morning_violation = time(9, 30)

    lunch_start = time(12, 0)
    lunch_end = time(13, 15)

    afternoon_warning = time(13, 15)
    afternoon_violation = time(13, 30)

    overtime_time = time(18, 0)

    # -------------------------------
    # LUNCH BREAK (NO PENALTY)
    # -------------------------------
    if lunch_start <= current_t <= lunch_end:
        return f"{event_type} (Lunch Break - No Warning)"

    # -------------------------------
    # CHECK-IN LOGIC
    # -------------------------------
    if event_type == "CHECK-IN":

        # MORNING RULES
        if current_t < lunch_start:
            if current_t > morning_violation:
                return "VIOLATION: Late Entry (Morning)"
            elif current_t > morning_warning:
                return "WARNING: Late (Morning)"
            else:
                return "CHECK-IN"

        # AFTERNOON (POST-LUNCH) RULES
        else:
            if current_t > afternoon_violation:
                return "VIOLATION: Late Entry (Afternoon)"
            elif current_t > afternoon_warning:
                return "WARNING: Late (Afternoon)"
            else:
                return "CHECK-IN"

    # -------------------------------
    # CHECK-OUT LOGIC
    # -------------------------------
    elif event_type == "CHECK-OUT":
        if current_t > overtime_time:
            return "OVERTIME"
        else:
            return "CHECK-OUT"

    return event_type


def log_event(name, status):
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    with open("attendance_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"{timestamp} - {name} - {status}\n")

    print(f"📝 {name} -> {status}")


def save_new_face(face_encoding, known_encodings, known_names):
    if known_encodings:
        matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
        if True in matches:
            match_index = matches.index(True)
            print(f"⚠️ Already registered as '{known_names[match_index]}'")
            return None

    name = input("Enter name: ").strip()
    if not name:
        print("⚠️ Name cannot be empty")
        return None

    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()

    encoding_json = json.dumps(face_encoding.tolist())
    cursor.execute(
        "INSERT INTO users (name, face_vector) VALUES (?, ?)",
        (name, encoding_json)
    )

    conn.commit()
    conn.close()

    print(f"✅ {name} added successfully")
    return name


known_encodings, known_names = load_registered_faces()

color_dictionary = {}
last_seen = {}
user_status = {}

def get_color(name):
    if name == "Unknown":
        return (0, 0, 255)

    if name not in color_dictionary:
        color_dictionary[name] = (
            random.randint(0, 255),
            random.randint(150, 255),
            random.randint(0, 255)
        )
    return color_dictionary[name]


video_capture = cv2.VideoCapture(0)
video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

face_locations = []
face_encodings = []
face_names = []
frame_counter = 0

print("System Active | 's' = save | 'q' = quit")

while True:
    ret, frame = video_capture.read()
    if not ret:
        break

    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    if frame_counter % 3 == 0:
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        face_names = []
        current_time = datetime.now()

        for face_encoding in face_encodings:
            name = "Unknown"

            if known_encodings:
                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.55)
                face_distances = face_recognition.face_distance(known_encodings, face_encoding)

                if len(face_distances) > 0:
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        name = known_names[best_match_index]

            face_names.append(name)

            if name != "Unknown":
                if name not in last_seen or (current_time - last_seen[name]).total_seconds() > 10:

                    if name not in user_status or user_status[name] == "OUT":
                        event_type = "CHECK-IN"
                        user_status[name] = "IN"
                    else:
                        event_type = "CHECK-OUT"
                        user_status[name] = "OUT"

                    final_status = get_status_by_time(event_type, current_time)
                    log_event(name, final_status)
                    last_seen[name] = current_time

    frame_counter += 1

    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        color = get_color(name)

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)

        cv2.putText(frame, name, (left + 5, bottom - 10),
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1)

    cv2.imshow('Face Recognition System', frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('s') and len(face_encodings) > 0:
        new_person = save_new_face(face_encodings[0], known_encodings, known_names)
        if new_person:
            known_encodings, known_names = load_registered_faces()

    elif key == ord('q'):
        break

video_capture.release()
cv2.destroyAllWindows()