# Face Recognition Based Tracking System

This project is a real-time face recognition system developed using Python. It utilizes computer vision techniques to detect and recognize faces through a webcam, store facial data in a database, and log detection events.



## Features

- Real-time face detection using a webcam  
- Face recognition based on encoded facial features  
- SQLite database integration for storing user data  
- Ability to register new faces dynamically  
- Duplicate face detection prevention  
- User management (delete records)  
- Logging system for recognized individuals  
- Performance optimizations for smoother processing  



## Technologies Used

- Python  
- OpenCV  
- face_recognition  
- dlib  
- SQLite  
- NumPy  



## Installation

### Clone the repository
```bash
git clone https://github.com/EthemKesim/https://github.com/EthemKesim/Face-Recognation-Based-Tracking-System.git
cd PROJE FACE RECO
````

### Install dependencies

```bash
pip install face-recognation
pip install dlib-bin
pip install face-recognation --no-deps
```



## Setup

Initialize the database by running:

```bash
python setup_database.py
```

This will create the required SQLite database file (`face_records.db`).



## Usage

### Run the main recognition system

```bash
python main_recognation.py
```

Controls:

* Press `s` to save a new face
* Press `q` to quit



### Register a new face manually

```bash
python register_face.py
```

Controls:

* Press `s` to capture and save
* Press `q` to quit



### Test camera and face detection

```bash
python camera_test.py
```

This module allows testing of face detection without storing any data.



### Delete registered users

```bash
python delete_record.py
```

Displays all registered users and allows deletion by ID.



## Project Structure

```
├── main_recognation.py
├── register_face.py
├── delete_record.py
├── camera_test.py
├── setup_database.py
├── face_records.db
├── access_logs.txt
```



## System Overview

* The system captures frames from a webcam
* Faces are detected and converted into numerical encoding vectors
* These vectors are stored in a SQLite database
* Incoming faces are compared with stored encodings
* If a match is found, the corresponding name is displayed
* If no match is found, the face is labeled as unknown and can be registered
* Recognized faces are logged with timestamps



## Logging

Detected individuals are recorded in the `access_logs.txt` file along with timestamps.


## Performance Optimizations

* Frame resizing to reduce processing load
* Processing every third frame instead of every frame
* Reduced camera resolution for improved FPS



## Notes

* A functional webcam is required
* Adequate lighting conditions improve recognition accuracy
* Duplicate entries are restricted by encoding comparison
* Recognition tolerance can be adjusted in the code



## Future Improvements

* Graphical user interface
* Multi-camera support
* Cloud-based database integration
* Attendance tracking features

