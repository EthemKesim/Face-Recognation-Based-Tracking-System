import cv2
import face_recognition
import sqlite3
import numpy as np
import json
import random
from datetime import datetime

def load_registered_faces():
    """Loads all face encodings and names from the database."""
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

def log_event(name):
    """Saves the detection event to a text file with a timestamp."""
    timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    with open("access_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"{timestamp} - {name} detected.\n")
    print(f"📝 Log saved: {name}")

def save_new_face(face_encoding, known_encodings, known_names):
    """Validates and saves a new face to the database."""
    # STEP 1: Check if this face already exists using encodings
    if known_encodings:
        matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
        if True in matches:
            match_index = matches.index(True)
            print(f"⚠️ Action Denied: This person is already registered as '{known_names[match_index]}'.")
            return None

    # STEP 2: Ask for a name and check uniqueness
    name = input("New face detected! Enter name to save: ").strip()
    if not name:
        print("⚠️ Registration cancelled: Name cannot be empty.")
        return None

    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()
    try:
        encoding_json = json.dumps(face_encoding.tolist())
        cursor.execute("INSERT INTO users (name, face_vector) VALUES (?, ?)", (name, encoding_json))
        conn.commit()
        print(f"✅ Success! {name} has been added to the system.")
        conn.close()
        return name
    except sqlite3.IntegrityError:
        print(f"⚠️ Error: The name '{name}' is already in use.")
        conn.close()
        return None

# Initial setup
known_encodings, known_names = load_registered_faces()
color_dictionary = {}
last_seen = {}

def get_color(name):
    if name == "Unknown": return (0, 0, 255) # Red for unknown
    if name not in color_dictionary:
        color_dictionary[name] = (random.randint(0, 255), random.randint(150, 255), random.randint(0, 255))
    return color_dictionary[name]

video_capture = cv2.VideoCapture(0)
# Lower resolution for higher FPS
video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

face_locations = []
face_encodings = []
face_names = []
frame_counter = 0 

print("System Active. Press 's' to Save New Face | 'q' to Quit")

while True:
    ret, frame = video_capture.read()
    if not ret: break

    # Performance optimization: Resize frame to 1/4
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Process only every 3rd frame to save CPU
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

            # Log every 10 seconds per recognized person
            if name != "Unknown":
                if name not in last_seen or (current_time - last_seen[name]).seconds > 60:
                    log_event(name)
                    last_seen[name] = current_time

    frame_counter += 1

    # Draw the results on the original frame
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= 4; right *= 4; bottom *= 4; left *= 4
        color = get_color(name)
        
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 5, bottom - 10), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1)

    cv2.imshow('Face Recognition System', frame)

    key = cv2.waitKey(1) & 0xFF
    
    # Save button logic
    if key == ord('s') and len(face_encodings) > 0:
        new_person = save_new_face(face_encodings[0], known_encodings, known_names)
        if new_person:
            # Refresh face data without restarting
            known_encodings, known_names = load_registered_faces()

    elif key == ord('q'):
        break

video_capture.release()
cv2.destroyAllWindows()