# Face Recognition Based Tracking System

## Overview

This project is a real-time **face recognition and attendance tracking system** built with Python. It detects and recognizes faces through a webcam, stores user data in a SQLite database, and logs attendance events automatically.

In addition to the core Python system, the project includes a **local web dashboard** that allows monitoring attendance data in a more user-friendly way.

The system has been organized and cleaned while preserving all working functionality.



## Features

### Core System (Python)

* Real-time face detection and recognition via webcam
* Face registration system
* Duplicate face detection prevention
* SQLite database integration
* Automatic attendance logging
* Simple user management (add/delete)
* Performance optimizations for smoother processing

### Web Dashboard (Local)

* View attendance logs in a structured format
* Read data from the main database and log file
* Clean separation between backend and frontend
* Lightweight and easy to run locally



## Technologies Used

* Python
* OpenCV
* face_recognition
* dlib
* SQLite
* NumPy
* HTML, CSS, JavaScript (Dashboard)
* Flask / lightweight backend (dashboard)



## How the System Works

### 1. Face Registration

* Run `register_face.py`
* Capture a new user's face via webcam
* Encode facial features
* Store data in `face_records.db`

### 2. Face Recognition & Attendance

* Run `main_recognition.py`
* Webcam starts and detects faces in real-time
* If a face matches:

  * The person's name is identified
  * Entry is logged in `attendance_logs.txt`
* Prevents duplicate logging within a short period

### 3. Data Storage

* `face_records.db` → stores registered users
* `attendance_logs.txt` → stores attendance records



## Main Application Files

* `main_recognition.py` → Real-time recognition & attendance logging
* `register_face.py` → Add new users
* `delete_record.py` → Delete users
* `camera_test.py` → Test camera and detection
* `setup_database.py` → Initialize database



## Web Dashboard

The dashboard provides a local interface to view attendance data.

### How it works

* Reads:

  * `face_records.db`
  * `attendance_logs.txt`
* Does **not modify core system data (read-only)**

### Run the dashboard

```bash
cd web-dashboard
python run_dashboard.py
```

Then open:

```
http://127.0.0.1:8000
```

---

## Project Structure

```
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

```
