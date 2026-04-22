# Face Recognition Based Tracking System

This project is a working Python face recognition and attendance tracking system. The cleanup in this repository keeps the existing camera, registration, recognition, database, and attendance log behavior intact while making the folder layout easier to follow.

## Main Application Files

- `main_recognition.py`: real-time recognition and attendance logging
- `register_face.py`: manual face registration
- `delete_record.py`: registered user deletion utility
- `camera_test.py`: camera and face detection test
- `setup_database.py`: SQLite table initialization

## Data Files

- `face_records.db`: live SQLite database used by the app
- `attendance_logs.txt`: live attendance log written by the recognition flow

## Dashboard

The dashboard lives in `web-dashboard/` and reads the root `face_records.db`, `attendance_logs.txt`, and `main_recognition.py` files in read-only mode.

Run it with:

```bash
cd web-dashboard
python run_dashboard.py
```

Then open `http://127.0.0.1:8000`.

## Project Structure

```text
.
|-- main_recognition.py
|-- register_face.py
|-- delete_record.py
|-- camera_test.py
|-- setup_database.py
|-- face_records.db
|-- attendance_logs.txt
|-- web-dashboard/
|   |-- backend/
|   |-- frontend/
|   `-- runtime_logs/
`-- legacy/
    `-- duplicate_project_snapshot/
```

## Notes

- The root database and log files are the active source of truth.
- `legacy/duplicate_project_snapshot/` stores the older duplicate copy safely for reference.
- `web-dashboard/runtime_logs/` stores dashboard runtime log artifacts to keep the main folder clean.
