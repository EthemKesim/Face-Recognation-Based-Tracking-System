import cv2
import face_recognition
import sqlite3
import numpy as np
import json

def register_new_face():
    # Connect to the database
    conn = sqlite3.connect('face_records.db')
    cursor = conn.cursor()

    video_capture = cv2.VideoCapture(0)
    print("Camera started. Press 's' to capture and save, 'q' to quit.")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        # Display instructions on screen
        cv2.putText(frame, "Press 's' to Save | 'q' to Quit", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow('Register Face', frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            # Find faces in the current frame
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            if len(face_encodings) > 0:
                name = input("Enter the name for this person: ")
                # Take the first face found
                encoding_json = json.dumps(face_encodings[0].tolist())
                
                cursor.execute("INSERT INTO users (name, face_vector) VALUES (?, ?)", (name, encoding_json))
                conn.commit()
                print(f"Success! {name} has been registered.")
            else:
                print("No face detected! Please try again.")

        elif key == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()
    conn.close()

if __name__ == "__main__":
    register_new_face()