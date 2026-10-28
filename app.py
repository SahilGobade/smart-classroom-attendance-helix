from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from flask import Flask, redirect, render_template, request, send_file, url_for

app = Flask(__name__)

PROJECT_DIR = Path(__file__).resolve().parent
DB_FILE = PROJECT_DIR / "attendance.db"
PHOTO_DIR = PROJECT_DIR / "registered_faces"
ATTENDANCE_SCRIPT = PROJECT_DIR / "attendance.py"
LOG_DIR = PROJECT_DIR / "logs"
CAMERA_STATUS_FILE = LOG_DIR / "camera_status.txt"
CAMERA_LOG_FILE = LOG_DIR / "camera_session.log"
EXPORT_SCRIPT = PROJECT_DIR / "export_attendance.mjs"
NODE_EXECUTABLE = (
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/"
    / "dependencies/node/bin/node.exe"
)
attendance_process = None
attendance_log_handle = None


def camera_status():
    if CAMERA_STATUS_FILE.exists():
        return CAMERA_STATUS_FILE.read_text(encoding="utf-8").strip()
    return "No camera session has been started yet."


def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            student_name TEXT NOT NULL
        )
        """
    )
    return connection


def registered_student_ids():
    if not PHOTO_DIR.is_dir():
        return set()
    return {
        photo.stem
        for photo in PHOTO_DIR.iterdir()
        if photo.is_file() and photo.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    }


def valid_report_date(value):
    """Return a safe selected date, defaulting to the current local date."""
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def get_dashboard_data(selected_date=None):
    """Build a single latest attendance record for every student for today."""
    report_date = valid_report_date(selected_date)
    student_ids = registered_student_ids()

    with get_connection() as connection:
        name_rows = connection.execute(
            "SELECT student_id, student_name FROM students"
        ).fetchall()
        names = {row["student_id"]: row["student_name"] for row in name_rows}

        event_rows = connection.execute(
            """
            SELECT id, student_id, event_type, event_time, face_distance
            FROM attendance_events
            WHERE event_time LIKE ?
            ORDER BY event_time DESC, id DESC
            """,
            (report_date + "%",),
        ).fetchall()
        attendance_rows = connection.execute(
            """
            SELECT DISTINCT student_id, substr(event_time, 1, 10) AS attendance_date
            FROM attendance_events
            WHERE upper(event_type) = 'IN'
            ORDER BY attendance_date ASC, student_id ASC
            """
        ).fetchall()

    events = [dict(row) for row in event_rows]
    attendance_rows = [dict(row) for row in attendance_rows]
    student_ids.update(names)
    student_ids.update(event["student_id"] for event in events)
    student_ids.update(row["student_id"] for row in attendance_rows)

    # Rows are newest first: retain only a student's most recent mark today.
    latest_by_student = {}
    latest_in = {}
    latest_out = {}
    for event in events:
        student_id = event["student_id"]
        latest_by_student.setdefault(student_id, event)
        if event["event_type"].upper() == "IN":
            latest_in.setdefault(student_id, event)
        elif event["event_type"].upper() == "OUT":
            latest_out.setdefault(student_id, event)

    students = []
    for student_id in sorted(student_ids):
        latest = latest_by_student.get(student_id)
        in_mark = latest_in.get(student_id)
        out_mark = latest_out.get(student_id)
        students.append({
            "student_id": student_id,
            "student_name": names.get(student_id, "Not set"),
            "last_mark": latest["event_type"].upper() if latest else "Not marked",
            "last_time": latest["event_time"] if latest else "—",
            "in_time": in_mark["event_time"] if in_mark else "Not marked",
            "out_time": out_mark["event_time"] if out_mark else "Not marked",
        })

    def build_mark_list(event_map):
        return [
            {
                "student_id": student_id,
                "student_name": names.get(student_id, "Not set"),
                "event_time": event["event_time"],
            }
            for student_id, event in sorted(
                event_map.items(), key=lambda item: item[1]["event_time"], reverse=True
            )
        ]

    # An IN mark means the student attended that day. Every recorded IN day
    # is treated as a class day for the 75% attendance calculation.
    class_days = {row["attendance_date"] for row in attendance_rows}
    present_dates = {}
    for row in attendance_rows:
        present_dates.setdefault(row["student_id"], set()).add(row["attendance_date"])

    attendance_summary = []
    for student_id in sorted(student_ids):
        days_present = len(present_dates.get(student_id, set()))
        percentage = round(days_present * 100 / len(class_days), 1) if class_days else 0
        attendance_summary.append({
            "student_id": student_id,
            "student_name": names.get(student_id, "Not set"),
            "days_present": days_present,
            "class_days": len(class_days),
            "attendance_percentage": percentage,
            "criteria_status": "Meets 75%" if percentage >= 75 else "Below 75%",
        })

    below_criteria = [
        student for student in attendance_summary
        if student["attendance_percentage"] < 75
    ]

    return {
        "today": report_date,
        "students": students,
        "in_entries": build_mark_list(latest_in),
        "out_entries": build_mark_list(latest_out),
        "in_count": len(latest_in),
        "out_count": len(latest_out),
        "student_count": len(students),
        "attendance_summary": attendance_summary,
        "class_days": len(class_days),
        "criteria_count": len(attendance_summary) - len(below_criteria),
        "below_criteria": below_criteria,
        "events": [
            {
                **event,
                "student_name": names.get(event["student_id"], "Not set"),
            }
            for event in events
        ],
    }


@app.route("/")
def dashboard():
    global attendance_process, attendance_log_handle
    if attendance_process is not None and attendance_process.poll() is not None:
        attendance_process = None
        if attendance_log_handle is not None:
            attendance_log_handle.close()
            attendance_log_handle = None

    selected_date = valid_report_date(request.args.get("date"))
    return render_template(
        "dashboard.html",
        **get_dashboard_data(selected_date),
        camera_running=attendance_process is not None,
        camera_status=camera_status(),
    )


@app.get("/export")
def export_attendance():
    """Download a daily attendance report in Excel format."""
    report = get_dashboard_data(request.args.get("date"))
    payload = {
        "date": report["today"],
        "stats": {
            "studentCount": report["student_count"],
            "inCount": report["in_count"],
            "outCount": report["out_count"],
        },
        "students": report["students"],
        "attendanceSummary": report["attendance_summary"],
        "events": report["events"],
    }

    temporary_dir = Path(tempfile.mkdtemp(prefix="attendance_export_"))
    input_file = temporary_dir / "report.json"
    output_file = temporary_dir / f"attendance_{report['today']}.xlsx"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    node = NODE_EXECUTABLE if NODE_EXECUTABLE.exists() else "node"
    try:
        subprocess.run(
            [str(node), str(EXPORT_SCRIPT), str(input_file), str(output_file)],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        return f"Could not create the Excel report: {error}", 500

    report_bytes = output_file.read_bytes()
    shutil.rmtree(temporary_dir, ignore_errors=True)
    return send_file(
        BytesIO(report_bytes),
        as_attachment=True,
        download_name=f"attendance_{report['today']}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/students")
def save_student():
    student_id = request.form.get("student_id", "").strip().upper()
    student_name = request.form.get("student_name", "").strip()
    if student_id and student_name:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO students (student_id, student_name)
                VALUES (?, ?)
                ON CONFLICT(student_id) DO UPDATE SET student_name = excluded.student_name
                """,
                (student_id, student_name),
            )
    return redirect(url_for("dashboard"))


@app.post("/start/<entry_type>")
def start_attendance(entry_type):
    global attendance_process, attendance_log_handle
    entry_type = entry_type.upper()
    if entry_type not in {"IN", "OUT"}:
        return "Unknown attendance type.", 400

    if attendance_process is not None and attendance_process.poll() is not None:
        attendance_process = None
        if attendance_log_handle is not None:
            attendance_log_handle.close()
            attendance_log_handle = None

    if attendance_process is None:
        LOG_DIR.mkdir(exist_ok=True)
        CAMERA_STATUS_FILE.write_text(
            f"Starting {entry_type} attendance camera...", encoding="utf-8"
        )
        attendance_log_handle = CAMERA_LOG_FILE.open("w", encoding="utf-8")
        attendance_process = subprocess.Popen(
            [
                sys.executable, "-u", str(ATTENDANCE_SCRIPT),
                "--mode", entry_type,
                "--status-file", str(CAMERA_STATUS_FILE),
            ],
            cwd=PROJECT_DIR,
            stdout=attendance_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
