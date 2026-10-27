
# Smart Classroom Attendance System

**Team Helix — Innovation and Design Thinking (IDT)**

## About
A Python-based classroom attendance prototype using webcam face recognition to record student entry and exit events.

## Features
- Webcam face recognition using DeepFace
- Entry and exit attendance recording
- SQLite database for attendance records
- Flask teacher dashboard
- Student name registration
- Attendance summary and Excel export

## Technologies
- Python
- OpenCV
- DeepFace with ArcFace
- SQLite
- Flask
- HTML and CSS
- Node.js for Excel report generation

## Setup on Windows 11

1. Install Python 3.11 and Node.js.
2. Create a virtual environment:

   `py -3.11 -m venv .venv`

3. Activate it:

   `.\.venv\Scripts\Activate.ps1`

4. Install Python libraries:

   `pip install -r requirements.txt`

5. Add consented student reference photos to `registered_faces/`.
   Example: `S001.jpg`, `S002.jpg`.

6. Start the attendance program:

   `python attendance.py`

7. In a second terminal, start the dashboard:

   `python app.py`

8. Open http://127.0.0.1:5000 in your browser.

## Limitations
This is an educational prototype. Face recognition and entry/exit detection may make errors. Verify attendance records before official use.

## Team
**Team Lead:** Sahil V. Gobade

**Team Helix members:** Vishesh Mishra, Vansh Dholakia, Anirudha Deshmukh, Gargi Dhole, Palak Bhandari, Aayush Kumar, Dhruv Gandhi, and Unnati.
