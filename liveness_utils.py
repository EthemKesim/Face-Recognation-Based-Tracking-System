import cv2
import numpy as np
import dlib
from scipy.spatial import distance as dist

# -------------------------------
# SETTINGS & MODELS
# -------------------------------
RIGHT_EYE_POINTS = list(range(36, 42))
LEFT_EYE_POINTS = list(range(42, 48))

detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

# -------------------------------
# MATH HELPERS
# -------------------------------
def calculate_ear(eye):
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    ear = (A + B) / (2.0 * C)
    return ear

# -------------------------------
# LIVENESS & TEXTURE LOGIC
# -------------------------------
def check_liveness(frame, face_location):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # ROI: Only face areas
    top, right, bottom, left = face_location
    # Coordinates are within the frame
    top, bottom = max(0, top), min(frame.shape[0], bottom)
    left, right = max(0, left), min(frame.shape[1], right)
    
    face_roi = gray[top:bottom, left:right]
    
    # Laplacian Sharpness
    if face_roi.size > 0:
        laplacian_var = cv2.Laplacian(face_roi, cv2.CV_64F).var()
    else:
        laplacian_var = 0
    
    # Dlib landmarks
    rect = dlib.rectangle(left, top, right, bottom)
    shape = predictor(gray, rect)
    
    shape_np = np.zeros((68, 2), dtype="int")
    for i in range(0, 68):
        shape_np[i] = (shape.part(i).x, shape.part(i).y)

    left_eye = shape_np[LEFT_EYE_POINTS]
    right_eye = shape_np[RIGHT_EYE_POINTS]
    
    ear = (calculate_ear(left_eye) + calculate_ear(right_eye)) / 2.0
    
    return ear, laplacian_var

def is_fake_texture(laplacian_var, threshold=110): 
    if laplacian_var < threshold:
        return True
    return False