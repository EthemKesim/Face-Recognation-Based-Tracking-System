# Face Recognition Based Attendance Tracking System

A real-time face recognition-based employee attendance tracking system developed in Python. The system recognizes employees through a webcam, performs liveness detection using eye-blink verification and image sharpness analysis, and automatically records attendance events in an SQLite database. The project also includes a web-based administrative dashboard for monitoring and managing attendance records.

## Features

- Real-time face recognition using webcam
- Employee registration and management
- Eye-blink based liveness detection
- Anti-spoofing protection using image sharpness checks
- Automatic check-in and check-out tracking
- Attendance status classification (late arrivals, lunch breaks, after-hours departures)
- SQLite-based data storage
- Unknown face detection and management
- Secure admin authentication and session handling
- Manual attendance management
- Live camera monitoring station
- Demo time simulation for presentations and testing
- CSV and Excel report export
- Automated testing with Pytest

## Technologies Used

### Backend
- Python 3.10+
- SQLite
- OpenCV
- face_recognition
- dlib
- NumPy

### Frontend
- HTML5
- CSS3
- JavaScript

### Additional Libraries
- openpyxl (Excel export)
- pytest (testing)

## System Architecture

The project consists of two main components:

### Face Recognition Station
Handles:
- Face detection and recognition
- Liveness verification
- Attendance processing
- Unknown face monitoring

### Admin Dashboard
Provides:
- Attendance monitoring
- Employee management
- Report generation
- System configuration
- Administrative controls

## Project Structure

```text
.
├── main_recognition.py
├── attendance_station.py
├── database_utils.py
├── liveness_utils.py
├── time_override.py
├── delete_record.py
├── face_records.db
├── attendance_logs.txt
├── employee_images/
├── unknown_face_images/
├── shape_predictor_68_face_landmarks.dat
│
├── web-dashboard/
│   ├── run_dashboard.py
│   ├── backend/
│   │   ├── app.py
│   │   └── data_access.py
│   │
│   └── frontend/
│       ├── index.html
│       ├── login.html
│       ├── app.js
│       └── styles.css
│
└── tests/
```

## Installation

### 1. Create a Virtual Environment

**Windows**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS**

```bash
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install opencv-python face-recognition dlib numpy openpyxl pytest
```

> Note: Installation of `dlib` and `face_recognition` may require C++ build tools. Windows users may need Visual Studio Build Tools.

### 3. Download Landmark Model

Place the following file in the project root directory:

```text
shape_predictor_68_face_landmarks.dat
```

This model is required for eye-blink based liveness detection.

## Database

The system uses SQLite as its primary database.

Database file:

```text
face_records.db
```

Automatically created tables:

| Table | Purpose |
|---------|---------|
| users | Face encodings and user records |
| employees | Employee profiles |
| attendance_logs | Attendance history |
| admins | Dashboard administrators |
| settings | Attendance rules |
| unknown_faces | Unknown face detections |
| admin_activity_log | Administrative activities |

## Running the Face Recognition Application

Start the recognition system:

```bash
python main_recognition.py
```

### Usage

- The webcam starts automatically.
- Registered employees are recognized in real time.
- New check-ins require eye-blink verification.
- Automatic check-out is performed after the configured duration.
- Press **S** to register a new employee.
- Press **Q** to quit the application.

## Attendance Rules

| Time | Status |
|--------|--------|
| After 09:15 | Warning: Late (Morning) |
| After 09:30 | Violation: Late (Morning) |
| 12:00 – 13:15 | Lunch Break |
| After 13:30 | Warning: Late (Afternoon) |
| After 13:45 | Violation: Late (Afternoon) |
| After 18:00 | After-Hours Check-Out |

## Admin Dashboard

The dashboard is a lightweight local web application for attendance and employee management.

### Environment Variables

Create a `.env` file:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-password
SESSION_SECRET=your-random-secret
```

### Start Dashboard

```bash
cd web-dashboard
python run_dashboard.py
```

Open in your browser:

```text
http://127.0.0.1:8000
```

### Dashboard Features

- Attendance overview
- Employee management
- Manual check-in/check-out
- Attendance history
- Search and filtering
- CSV export
- Excel export
- Unknown face management
- Live camera station
- Admin activity logs
- Attendance rule configuration
- Demo time simulation

## Employee Registration

Employees can be added in two ways:

### Dashboard Registration

- Upload a photo
- Capture a photo using the webcam
- Automatically generate face encodings

### Face Recognition Station

While the application is running:

```text
Press S → Enter Employee Name
```

The system extracts facial features and stores them in the database.

## Unknown Face Detection

When an unregistered person is detected:

- An image can be saved in:

```text
unknown_face_images/
```

- Detection statistics are stored in the database.
- The dashboard displays unknown faces for administrator review.

## Testing

Run all tests:

```bash
pytest
```

### Test Coverage

- Database initialization
- Table migrations
- Admin authentication
- Employee CRUD operations
- Attendance logging
- Manual attendance operations
- Unknown face grouping
- Time override scenarios
- Check-in/check-out business rules

## Security Features

- Password hashing
- Session-based authentication
- Liveness detection
- Anti-spoofing verification
- Activity logging
- Unknown face monitoring

## Future Improvements

- Multi-camera support
- Cloud database integration
- Email notifications
- Mobile application support
- Role-based access control
- Advanced facial anti-spoofing techniques
- Real-time analytics dashboard
