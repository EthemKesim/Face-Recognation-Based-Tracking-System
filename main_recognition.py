import cv2
import face_recognition
import json
import numpy as np
import os
from datetime import datetime, time
from liveness_utils import check_liveness, is_fake_texture
from database_utils import init_db, insert_user, load_registered_faces, log_attendance_event

# -------------------------------
# SETTINGS & CONSTANTS
# -------------------------------
KNOWN_ENCODINGS, KNOWN_NAMES = load_registered_faces()
LIVENESS_STATUS = {} 
LAST_SEEN = {}         
FRAME_COUNTER = 0
LOG_FILE = "attendance_logs.txt" 

# -------------------------------
# TIME RULES
# -------------------------------
def get_status_by_time(event_type, current_dt):
    current_t = current_dt.time()
    morning_warning = time(9, 15)
    morning_violation = time(9, 30)
    lunch_start = time(12, 0)
    lunch_end = time(13, 15)
    
    if lunch_start <= current_t <= lunch_end:
        return f"{event_type} (Lunch Break)"
    return event_type

# -------------------------------
# TXT LOGGING MECHANIC
# -------------------------------
def log_to_txt(name, status, dt):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] Name: {name} | Status: {status}\n"
        f.write(log_entry)

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
    
    print(f"System Started. Logging to both DB and {LOG_FILE}")

    while True:
        ret, frame = video_capture.read()
        if not ret: break

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
                name = "Unknown"

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
                        
                        if LIVENESS_STATUS[i]:
                            display_name = actual_name
                            current_time = datetime.now()
                            
                            # Duplicate prevention (5 min)
                            if actual_name not in LAST_SEEN or (current_time - LAST_SEEN[actual_name]).total_seconds() > 300:
                                status = get_status_by_time("CHECK-IN", current_time)
                                
                                # 1. SQLITE LOGGING
                                log_attendance_event(actual_name, status, current_time)
                                
                                # 2. TXT LOGGING 
                                log_to_txt(actual_name, status, current_time)
                                
                                LAST_SEEN[actual_name] = current_time
                        else:
                            display_name = f"{actual_name} (Blink)"
                else:
                    display_name = "Unknown"
                
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

        if key == ord('q'): break

    video_capture.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    init_db()
    run_recognition()