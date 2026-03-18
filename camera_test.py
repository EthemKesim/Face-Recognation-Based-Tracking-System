import cv2
import face_recognition

def run_camera_test():
    video_capture = cv2.VideoCapture(0)
    print("Testing face detection... Press 'q' to stop.")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        # Scale down for faster processing
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # Detect face locations
        face_locations = face_recognition.face_locations(rgb_small_frame)

        # Draw a box around each face detected
        for (top, right, bottom, left) in face_locations:
            top *= 4; right *= 4; bottom *= 4; left *= 4
            cv2.rectangle(frame, (left, top), (right, bottom), (255, 0, 0), 2)
            cv2.putText(frame, "Face Detected", (left, top - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        cv2.imshow('Face Detection Test', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_camera_test()