import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import cv2
from deepface import DeepFace

FACE_DATABASE = "registered_faces"
ATTENDANCE_DATABASE = "attendance.db"
CAMERA_INDEX = 0
PROCESS_EVERY_N_FRAMES = 8
MODEL_NAME = "ArcFace"


def get_entry_type():
    parser = argparse.ArgumentParser(
        description="Record one type of classroom attendance."
    )
    parser.add_argument(
        "--mode", choices=("IN", "OUT"),
        help="Record only IN or only OUT attendance.",
    )
    mode = parser.parse_args().mode

    while mode is None:
        mode = input("Choose attendance type (IN/OUT): ").strip().upper()
        if mode not in {"IN", "OUT"}:
            print("Please enter IN or OUT.")
            mode = None

    return mode


def check_opencv_gui():
    """Stop early when a headless OpenCV build is installed."""
    try:
        cv2.namedWindow("OpenCV GUI check", cv2.WINDOW_NORMAL)
        cv2.destroyWindow("OpenCV GUI check")
    except cv2.error as error:
        raise SystemExit(
            "OpenCV GUI support is unavailable. Remove all OpenCV packages "
            "and install the GUI-enabled opencv-python package.\n\n"
            "Run:\n"
            "python -m pip uninstall -y opencv-python "
            "opencv-python-headless opencv-contrib-python "
            "opencv-contrib-python-headless\n"
            "python -m pip install --upgrade opencv-python\n\n"
            f"OpenCV reported: {error}"
        ) from error


def main():
    entry_type = get_entry_type()
    check_opencv_gui()

    photo_files = [
        photo for photo in Path(FACE_DATABASE).iterdir()
        if photo.is_file() and photo.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ] if Path(FACE_DATABASE).is_dir() else []

    if not photo_files:
        raise SystemExit(
            "No reference photos found in registered_faces. "
            "Add images such as S001.jpg and try again."
        )

    connection = sqlite3.connect(ATTENDANCE_DATABASE)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            face_distance REAL
        )
        """
    )
    connection.commit()

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        connection.close()
        raise SystemExit(
            "Could not open webcam. Check camera permissions "
            "or try CAMERA_INDEX = 1."
        )

    frame_number = 0
    visible_faces = []
    recorded_students = set()
    refresh_database = True
    last_error = None

    print(f"{entry_type} attendance session started.")
    print("Each recognised student is recorded once in this session.")
    print("Press Q in the camera window to stop.")

    try:
        while True:
            success, frame = camera.read()
            if not success:
                print("Could not read a frame from the webcam.")
                break

            frame = cv2.resize(frame, (640, 480))

            if frame_number % PROCESS_EVERY_N_FRAMES == 0:
                try:
                    results = DeepFace.find(
                        img_path=frame,
                        db_path=FACE_DATABASE,
                        model_name=MODEL_NAME,
                        detector_backend="opencv",
                        enforce_detection=False,
                        silent=True,
                        refresh_database=refresh_database,
                        return_type="dict",
                    )
                    refresh_database = False
                    last_error = None
                    visible_faces = []

                    for face_results in results:
                        if not face_results:
                            continue

                        match = face_results[0]
                        student_id = Path(str(match.get("identity", ""))).stem
                        x = int(match.get("source_x", 0))
                        y = int(match.get("source_y", 0))
                        width = int(match.get("source_w", 0))
                        height = int(match.get("source_h", 0))
                        if not student_id or width <= 0 or height <= 0:
                            continue

                        already_recorded = student_id in recorded_students
                        visible_faces.append((student_id, x, y, width, height, already_recorded))

                        if already_recorded:
                            continue

                        event_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        distance = match.get("distance")
                        if distance is not None:
                            distance = float(distance)

                        connection.execute(
                            """
                            INSERT INTO attendance_events
                            (student_id, event_type, event_time, face_distance)
                            VALUES (?, ?, ?, ?)
                            """,
                            (student_id, entry_type, event_time, distance),
                        )
                        connection.commit()
                        recorded_students.add(student_id)
                        print(f"{student_id}: {entry_type} recorded at {event_time}")

                except Exception as error:
                    message = f"{type(error).__name__}: {error}"
                    if message != last_error:
                        print("Recognition error:", message)
                        last_error = message

            cv2.putText(
                frame, f"{entry_type} ATTENDANCE - Press Q to stop", (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
            )
            for student_id, x, y, width, height, already_recorded in visible_faces:
                color = (0, 255, 0) if already_recorded else (0, 200, 255)
                label = f"{student_id} - {'Recorded' if already_recorded else 'Recording'}"
                cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
                cv2.putText(
                    frame, label, (x, max(y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                )

            cv2.imshow(f"Smart Classroom {entry_type} Attendance", frame)
            frame_number += 1
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        connection.close()
        print(f"{entry_type} attendance session stopped.")


if __name__ == "__main__":
    main()
