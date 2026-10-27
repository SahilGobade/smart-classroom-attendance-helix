import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node export_attendance.mjs <input.json> <output.xlsx>");
}

const report = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const summary = workbook.worksheets.add("Daily Attendance");
const criteria = workbook.worksheets.add("Attendance Criteria");
const eventLog = workbook.worksheets.add("Event Log");

const titleFormat = {
  font: { name: "Arial", size: 14, bold: true, color: "#1F2937" },
};
const headerFormat = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};

summary.showGridLines = false;
summary.getRange("A2").values = [["Smart Classroom Attendance"]];
summary.getRange("A2").format = titleFormat;
summary.getRange("A3").values = [[`Daily report: ${report.date}`]];
summary.getRange("A3").format = { font: { name: "Arial", size: 10, italic: true, color: "#4B5563" } };
summary.getRange("A5:C5").values = [["Registered Students", "Marked IN", "Marked OUT"]];
summary.getRange("A5:C5").format = headerFormat;
summary.getRange("A6:C6").values = [[report.stats.studentCount, report.stats.inCount, report.stats.outCount]];
summary.getRange("A8:D8").values = [["Student ID", "Student Name", "Latest Mark", "Marked At"]];
summary.getRange("A8:D8").format = headerFormat;
summary.getRange("A9").writeValues(report.students.map((student) => [
  student.student_id,
  student.student_name,
  student.last_mark,
  student.last_time,
]));
if (report.students.length > 0) {
  summary.tables.add(`A8:D${8 + report.students.length}`, true, "DailyAttendanceTable");
}
summary.getRange("A:D").format.font = { name: "Arial", size: 10 };
summary.getRange("A:D").format.autofitColumns();
summary.getRange("A:A").format.columnWidth = 14;
summary.getRange("B:B").format.columnWidth = 24;
summary.getRange("C:C").format.columnWidth = 14;
summary.getRange("D:D").format.columnWidth = 22;
summary.freezePanes.freezeRows(8);

criteria.showGridLines = false;
criteria.getRange("A2").values = [["Attendance Criteria"]];
criteria.getRange("A2").format = titleFormat;
criteria.getRange("A3").values = [["Students must maintain at least 75% attendance across recorded class days."]];
criteria.getRange("A3").format = { font: { name: "Arial", size: 10, italic: true, color: "#4B5563" } };
criteria.getRange("A5:F5").values = [[
  "Student ID", "Student Name", "Days Present", "Recorded Class Days", "Attendance %", "75% Criteria",
]];
criteria.getRange("A5:F5").format = headerFormat;
if (report.attendanceSummary.length > 0) {
  criteria.getRange("A6").writeValues(report.attendanceSummary.map((student) => [
    student.student_id,
    student.student_name,
    student.days_present,
    student.class_days,
    student.attendance_percentage / 100,
    student.criteria_status,
  ]));
  criteria.tables.add(`A5:F${5 + report.attendanceSummary.length}`, true, "AttendanceCriteriaTable");
}
criteria.getRange("A:F").format.font = { name: "Arial", size: 10 };
criteria.getRange("E6:E1000").format.numberFormat = "0.0%";
criteria.getRange("A:F").format.autofitColumns();
criteria.getRange("A:A").format.columnWidth = 14;
criteria.getRange("B:B").format.columnWidth = 24;
criteria.getRange("C:D").format.columnWidth = 19;
criteria.getRange("E:E").format.columnWidth = 15;
criteria.getRange("F:F").format.columnWidth = 18;
criteria.freezePanes.freezeRows(5);

eventLog.showGridLines = false;
eventLog.getRange("A2").values = [["Attendance Event Log"]];
eventLog.getRange("A2").format = titleFormat;
eventLog.getRange("A3").values = [[`Date: ${report.date}`]];
eventLog.getRange("A3").format = { font: { name: "Arial", size: 10, italic: true, color: "#4B5563" } };
eventLog.getRange("A5:D5").values = [["Student ID", "Student Name", "Event", "Event Time"]];
eventLog.getRange("A5:D5").format = headerFormat;
if (report.events.length > 0) {
  eventLog.getRange("A6").writeValues(report.events.map((event) => [
    event.student_id,
    event.student_name,
    event.event_type,
    event.event_time,
  ]));
  eventLog.tables.add(`A5:D${5 + report.events.length}`, true, "AttendanceEventsTable");
} else {
  eventLog.getRange("A6").values = [["No attendance records for this date.", "", "", ""]];
  eventLog.getRange("A6:D6").format = {
    font: { name: "Arial", size: 10, italic: true, color: "#4B5563" },
  };
}
eventLog.getRange("A:D").format.font = { name: "Arial", size: 10 };
eventLog.getRange("A:D").format.autofitColumns();
eventLog.getRange("A:A").format.columnWidth = 14;
eventLog.getRange("B:B").format.columnWidth = 24;
eventLog.getRange("C:C").format.columnWidth = 12;
eventLog.getRange("D:D").format.columnWidth = 22;
eventLog.freezePanes.freezeRows(5);

workbook.recalculate();
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
