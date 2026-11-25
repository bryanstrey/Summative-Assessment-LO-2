# =========================================================
# tests/run_tests.py - Test record for the ST4 workflow
# =========================================================
# Run from the project root:   python tests/run_tests.py
#
# Each test runs the real workflow (run_report.main) on a copy of the
# inputs inside tests/test_runs/<test>/ and records: setup, expected
# result, actual result and pass/fail. The record is written to
# docs/st4_test_record.md. The original data in data/raw/st4 is only
# copied, never changed.
#
# Expected values below were calculated manually from the business rules
# (see HAND_CALCULATION), without using the program's own functions.
# =========================================================

import contextlib
import hashlib
import io
import platform
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
import run_report  # noqa: E402  (the workflow under test)

RAW = PROJECT / "data" / "raw" / "st4"
SANDBOX = PROJECT / "tests" / "test_runs"
RECORD = PROJECT / "docs" / "st4_test_record.md"
FILE_1 = "enrollments_2026-10-21.csv"
FILE_2 = "enrollments_2026-10-22.csv"

# id, course and base price, discounts that apply, tuition, fee, semester total
HAND_CALCULATION = [
    ("E-1001", "English 450", "sibling 10% + upfront 5% + PROMO5 5% = 20%", 360.00, 150.00, 2310.00),
    ("E-1002", "Spanish 420", "none = 0% (renewal: fee waived)", 420.00, 0.00, 2520.00),
    ("E-1003", "French 480", "sibling 10% = 10%", 432.00, 150.00, 2742.00),
    ("E-1004", "English 450", "upfront 5% = 5%", 427.50, 150.00, 2715.00),
    ("E-1005", "Spanish 420", "PROMO5 5% = 5%", 399.00, 150.00, 2544.00),
    ("E-1006", "French 480", "upfront 5% = 5% (renewal: fee waived)", 456.00, 0.00, 2736.00),
    ("E-1007", "English 450", "sibling 10% + upfront 5% + PROMO5 5% = 20% (renewal)", 360.00, 0.00, 2160.00),
    ("E-1008", "Spanish 420", "none = 0%", 420.00, 150.00, 2670.00),
    ("E-1009", "French 480", "sibling 10% + upfront 5% = 15%", 408.00, 150.00, 2598.00),
    ("E-1010", "English 450", "PROMO10 not recognized = 0%", 450.00, 150.00, 2850.00),
]
EXPECTED_TOTALS = {row[0]: row[5] for row in HAND_CALCULATION}
EXPECTED_REVENUE = 25845.00      # sum of the ten semester totals
EXPECTED_DISCOUNTS = 2205.00     # (base - tuition) x 6, summed
EXPECTED_BY_COURSE = [("English", 4, 10035.00), ("French", 3, 8076.00), ("Spanish", 3, 7734.00)]


# ---------- HELPERS ----------

def hashes(folder):
    """SHA-256 of every file under a folder, keyed by relative path."""
    folder = Path(folder)
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*")) if path.is_file()
    }


def new_case(name):
    """Fresh input/output folders for one test."""
    base = SANDBOX / name
    inp, out = base / "input", base / "output"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    return inp, out


def copy_raw(inp):
    for path in sorted(RAW.glob("enrollments_*.csv")):
        shutil.copy2(path, inp / path.name)


def edit_file(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"setup error: '{old}' not found in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def run(inp, out):
    """Run the workflow and capture what it prints.

    An unexpected exception (a program defect, which the workflow re-raises on
    purpose) is recorded as exit code 2 so the test fails instead of stopping.
    """
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = run_report.main(inp, out)
    except Exception as error:
        code = 2
        buffer.write(f"UNEXPECTED ERROR: {error!r}\n")
    return code, buffer.getvalue()


def run_folders(out, kind):
    folder = out / kind
    return sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def log_line(folder, word):
    """First log line containing a word (for example FAILED)."""
    for line in (folder / "run.log").read_text(encoding="utf-8").splitlines():
        if word in line:
            return line.split(" ", 3)[-1] if line.count(" ") >= 3 else line
    return ""


def rel(path):
    return Path(path).relative_to(PROJECT).as_posix()


class Result:
    """Collects checks for one test; the test passes only if every check passes."""

    def __init__(self, test_id, condition, setup, expected):
        self.test_id, self.condition, self.setup, self.expected = test_id, condition, setup, expected
        self.checks, self.actual, self.evidence = [], "", ""

    def ok(self, description, condition):
        self.checks.append((description, bool(condition)))

    @property
    def passed(self):
        return all(result for _, result in self.checks)

    def failing(self):
        return [description for description, result in self.checks if not result]


def failed_run_checks(r, out, code, text, expected_words):
    """Checks shared by every test where the run must fail cleanly."""
    done, failed = run_folders(out, "completed"), run_folders(out, "failed")
    r.ok("exit code is 1", code == 1)
    r.ok("no completed run folder", len(done) == 0)
    r.ok("one failed run folder", len(failed) == 1)
    message = log_line(failed[0], "FAILED") if failed else ""
    for word in expected_words:
        r.ok(f"error message mentions '{word}'", word in message)
    r.ok("console tells the user the run FAILED", "FAILED" in text)
    if failed:
        leftovers = [p.name for p in failed[0].iterdir() if p.name != "run.log"]
        r.ok("failed folder holds only the log (no outputs)", leftovers == [])
        r.evidence = rel(failed[0] / "run.log")
    history = pd.read_csv(out / "run_history.csv")
    r.ok("run_history.csv last row says FAILED", history["status"].iloc[-1] == "FAILED")
    return message, failed


# ---------- REQUIRED TESTS ----------

def test_valid_batch():
    r = Result("T1", "Valid selected batch",
               "Copies of the two original files (10 enrollments) in an empty input folder.",
               "Run COMPLETED with processed CSVs, workbook, report and log; every result equals "
               "the hand calculation; originals unchanged.")
    inp, out = new_case("T1_valid_batch")
    copy_raw(inp)
    raw_before = hashes(RAW)
    code, text = run(inp, out)
    done, failed = run_folders(out, "completed"), run_folders(out, "failed")
    r.ok("exit code is 0", code == 0)
    r.ok("one completed run, no failed run", len(done) == 1 and len(failed) == 0)
    r.ok("original files unchanged", hashes(RAW) == raw_before)
    if not done:
        r.actual = "no completed run was produced"
        return r
    folder = done[0]
    r.evidence = rel(folder)
    names = sorted(p.name for p in folder.rglob("*") if p.is_file())
    r.ok("outputs exist", names == [
        "enrollment_report.txt", "enrollment_workbook.xlsx", "enrollments_2026-10-21_processed.csv",
        "enrollments_2026-10-22_processed.csv", "run.log"])

    csv_data = pd.concat([pd.read_csv(p) for p in sorted((folder / "processed").glob("*.csv"))])
    by_id = dict(zip(csv_data["enrollment_id"], csv_data["semester_total"]))
    matches = sum(1 for key, value in EXPECTED_TOTALS.items() if abs(by_id.get(key, -1) - value) < 0.005)
    csv_total = round(csv_data["semester_total"].sum(), 2)
    r.ok("all 10 row totals equal the hand calculation", matches == 10)
    r.ok("CSV total equals hand total", csv_total == EXPECTED_REVENUE)
    r.ok("CSV rows carry their source filename",
         set(csv_data["source_file"]) == {FILE_1, FILE_2})

    sheets = pd.read_excel(folder / "enrollment_workbook.xlsx", sheet_name=None)
    wb_total = round(sheets["Enrollments"]["semester_total"].sum(), 2)
    summary = [(row.course, int(row.enrollments), round(row.semester_revenue, 2))
               for row in sheets["By_Course"].itertuples()]
    r.ok("workbook has the 3 sheets", list(sheets) == ["Enrollments", "By_Course", "Run_Info"])
    r.ok("workbook detail has 10 rows", len(sheets["Enrollments"]) == 10)
    r.ok("workbook total equals hand total", wb_total == EXPECTED_REVENUE)
    r.ok("summary equals hand calculation, sorted by revenue", summary == EXPECTED_BY_COURSE)

    report = (folder / "enrollment_report.txt").read_text(encoding="utf-8")
    report_total = float(re.search(r"Projected semester revenue \(USD\): ([0-9.]+)", report).group(1))
    report_discounts = float(re.search(r"Discounts granted \(USD\): ([0-9.]+)", report).group(1))
    r.ok("report total equals hand total", report_total == EXPECTED_REVENUE)
    r.ok("report discounts equal hand calculation", report_discounts == EXPECTED_DISCOUNTS)
    r.ok("report lists both source files", FILE_1 in report and FILE_2 in report)
    log = (folder / "run.log").read_text(encoding="utf-8")
    r.ok("log has STARTED, a WARNING for PROMO10 and COMPLETED",
         "STARTED" in log and "WARNING Unrecognized coupon 'PROMO10'" in log and "COMPLETED" in log)

    r.actual = (f"Exit code {code}; 1 completed run; {matches} of 10 row totals match; revenue in CSVs / "
                f"workbook / report = {csv_total:.2f} / {wb_total:.2f} / {report_total:.2f} "
                f"(hand: {EXPECTED_REVENUE:.2f}); discounts {report_discounts:.2f}; "
                "originals unchanged; log has 1 WARNING (PROMO10).")
    return r


def test_invalid_rule_value():
    r = Result("T2", "Invalid value for a business rule",
               f"File 1 valid; in {FILE_2} the course of E-1008 changed from Spanish to Italian "
               "(an unknown course).",
               "Failure with a useful error naming the file, line and value; no completed outputs; "
               "the valid first file produces nothing either (whole batch stops).")
    inp, out = new_case("T2_invalid_value")
    copy_raw(inp)
    edit_file(inp / FILE_2, "E-1008,Rafael Lima,Spanish", "E-1008,Rafael Lima,Italian")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_2, "Italian", "line(s) [4]"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"; failed folder has only run.log."
    return r


def test_missing_column():
    r = Result("T3", "Missing required column",
               f"File 1 valid; the 'course' column removed from {FILE_2}.",
               "Failure with an error naming the missing column and file; no completed outputs.")
    inp, out = new_case("T3_missing_column")
    copy_raw(inp)
    data = pd.read_csv(inp / FILE_2, dtype=str, keep_default_na=False).drop(columns=["course"])
    data.to_csv(inp / FILE_2, index=False)
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_2, "missing required column", "course"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"; failed folder has only run.log."
    return r


def test_no_matching_files():
    r = Result("T4", "No matching input files",
               "Input folder exists but contains only notes.txt and orders_2026-10-21.csv "
               "(no file named enrollments_*.csv).",
               "Failed run with a clear explanation of the selection rule; no completed outputs.")
    inp, out = new_case("T4_no_matching_files")
    (inp / "notes.txt").write_text("not an enrollment export\n", encoding="utf-8")
    shutil.copy2(RAW / FILE_1, inp / "orders_2026-10-21.csv")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, ["No files matching", "enrollments_*.csv"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"; failed folder has only run.log."
    return r


def test_second_run():
    r = Result("T5", "Same valid inputs, second run",
               "Two runs in a row on copies of the two original files, same output folder.",
               "Same results both times, in a new run folder; the first run's files are preserved "
               "byte for byte.")
    inp, out = new_case("T5_second_run")
    copy_raw(inp)
    code1, _ = run(inp, out)
    first = run_folders(out, "completed")[0]
    first_hashes = hashes(first)
    code2, _ = run(inp, out)
    done = run_folders(out, "completed")
    r.ok("both runs exit 0", code1 == 0 and code2 == 0)
    r.ok("two completed run folders with different names", len(done) == 2 and done[0].name != done[1].name)
    if len(done) != 2:
        r.actual = "second run did not complete"
        return r
    second = done[1]
    r.evidence = f"{rel(first)} and {rel(second)}"
    r.ok("first run's files unchanged after the second run", hashes(first) == first_hashes)
    same_csv = all(
        (first / "processed" / p.name).read_bytes() == p.read_bytes()
        for p in (second / "processed").glob("*.csv"))
    r.ok("processed CSVs identical in both runs", same_csv)
    a = pd.read_excel(first / "enrollment_workbook.xlsx", sheet_name=["Enrollments", "By_Course"])
    b = pd.read_excel(second / "enrollment_workbook.xlsx", sheet_name=["Enrollments", "By_Course"])
    r.ok("workbook values identical in both runs",
         a["Enrollments"].equals(b["Enrollments"]) and a["By_Course"].equals(b["By_Course"]))

    def stable_lines(folder):
        text = (folder / "enrollment_report.txt").read_text(encoding="utf-8")
        return [l for l in text.splitlines() if not l.startswith(("Run:", "Generated:"))]
    r.ok("report identical except run id and timestamp", stable_lines(first) == stable_lines(second))
    history = pd.read_csv(out / "run_history.csv")
    r.ok("run_history.csv lists two COMPLETED runs", list(history["status"]) == ["COMPLETED", "COMPLETED"])
    r.actual = (f"Exit codes {code1} and {code2}; two completed folders ({first.name}, {second.name}); "
                "CSVs, workbook values and report identical; first run's files unchanged; "
                "history lists 2 COMPLETED.")
    return r


# ---------- ADDITIONAL TESTS ----------

def test_duplicate_key():
    r = Result("A1", "Repeated business key across files",
               f"In {FILE_2}, enrollment_id E-1006 changed to E-1001 (already in {FILE_1}).",
               "Failure naming the repeated id and both file lines; no completed outputs.")
    inp, out = new_case("A1_duplicate_id")
    copy_raw(inp)
    edit_file(inp / FILE_2, "E-1006,", "E-1001,")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, ["Repeated enrollment_id", "E-1001", FILE_1, FILE_2])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_blank_name():
    r = Result("A2", "Blank required text",
               f"In {FILE_1}, the student_name of E-1003 left blank.",
               "Failure naming the column and CSV line; no completed outputs.")
    inp, out = new_case("A2_blank_name")
    copy_raw(inp)
    edit_file(inp / FILE_1, "E-1003,Ana Costa,", "E-1003,,")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_1, "blank student_name", "line(s) [4]"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_invalid_yes_no():
    r = Result("A3", "Value outside the allowed list",
               f"In {FILE_1}, sibling_enrolled of E-1004 changed from no to maybe.",
               "Failure listing the allowed values; no completed outputs.")
    inp, out = new_case("A3_invalid_yes_no")
    copy_raw(inp)
    edit_file(inp / FILE_1, "E-1004,Pedro Alves,English,no,", "E-1004,Pedro Alves,English,maybe,")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, ["sibling_enrolled", "maybe", "allowed values"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_missing_folder():
    r = Result("A4", "Missing input folder",
               "The input folder path does not exist.",
               "Failure naming the folder; no completed outputs.")
    _, out = new_case("A4_missing_folder")
    missing = SANDBOX / "A4_missing_folder" / "does_not_exist"
    code, text = run(missing, out)
    message, _ = failed_run_checks(r, out, code, text, ["Input folder not found"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_header_only_file():
    r = Result("A5", "File with a header but no rows",
               f"{FILE_2} replaced by its header line only.",
               "Failure saying the file has no data rows; no completed outputs.")
    inp, out = new_case("A5_header_only")
    copy_raw(inp)
    header = (inp / FILE_2).read_text(encoding="utf-8").splitlines()[0]
    (inp / FILE_2).write_text(header + "\n", encoding="utf-8")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_2, "no data rows"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_write_failure():
    r = Result("A6", "Output write fails; earlier output preserved",
               "A valid run completes first. A second run is forced to fail while writing the workbook "
               "(PermissionError raised in write_workbook).",
               "Second run FAILED; no completed folder for it and no final report; the first completed "
               "run is untouched; partial files stay in output/failed.")
    inp, out = new_case("A6_write_failure")
    copy_raw(inp)
    code1, _ = run(inp, out)
    first = run_folders(out, "completed")[0]
    first_hashes = hashes(first)

    original = run_report.write_workbook

    def broken(*args, **kwargs):
        raise PermissionError("simulated: workbook file is locked")
    run_report.write_workbook = broken
    try:
        code2, text = run(inp, out)
    finally:
        run_report.write_workbook = original

    done, failed = run_folders(out, "completed"), run_folders(out, "failed")
    r.ok("first run completed (exit 0)", code1 == 0)
    r.ok("second run exit code is 1", code2 == 1)
    r.ok("still exactly one completed run", len(done) == 1 and done[0] == first)
    r.ok("first run's files unchanged", hashes(first) == first_hashes)
    r.ok("one failed run folder", len(failed) == 1)
    message = ""
    if failed:
        message = log_line(failed[0], "FAILED")
        names = sorted(p.name for p in failed[0].rglob("*") if p.is_file())
        r.ok("failure reason logged", "PermissionError" in message or "locked" in message)
        r.ok("no final report or workbook in the failed folder",
             "enrollment_report.txt" not in names and "enrollment_workbook.xlsx" not in names)
        r.ok("partial processed CSVs kept only under failed/",
             any(n.endswith("_processed.csv") for n in names))
        r.evidence = rel(failed[0] / "run.log")
    history = pd.read_csv(out / "run_history.csv")
    r.ok("history shows COMPLETED then FAILED", list(history["status"]) == ["COMPLETED", "FAILED"])
    r.actual = (f"Exit codes {code1} then {code2}; completed runs: {len(done)} (first run untouched); "
                f"failed runs: {len(failed)}; logged: \"{message}\"; no report or workbook in the failed folder; "
                "history: COMPLETED, FAILED.")
    return r


def insert_blank_line_after_first_row(path):
    """Put a blank line after the first data row (so later rows move down one line)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(2, "")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_blank_line_traceability():
    r = Result("A7", "Blank line inside a file keeps true line numbers",
               f"A blank line inserted after E-1001 in {FILE_1}; every row after it moves down one line. "
               "Rows are otherwise valid.",
               "Run COMPLETED; the blank line is ignored; source_line equals the real file line "
               "(E-1002 on line 4, E-1005 on line 7).")
    inp, out = new_case("A7_blank_line_valid")
    copy_raw(inp)
    insert_blank_line_after_first_row(inp / FILE_1)
    code, text = run(inp, out)
    done = run_folders(out, "completed")
    r.ok("exit code is 0 and one completed run", code == 0 and len(done) == 1)
    lines_found = {}
    if done:
        data = pd.read_csv(done[0] / "processed" / "enrollments_2026-10-21_processed.csv")
        lines_found = dict(zip(data["enrollment_id"], data["source_line"]))
        r.evidence = rel(done[0] / "processed" / "enrollments_2026-10-21_processed.csv")
    r.ok("source_line matches the real file lines",
         lines_found == {"E-1001": 2, "E-1002": 4, "E-1003": 5, "E-1004": 6, "E-1005": 7})
    r.ok("revenue unchanged (blank line adds no enrollment)",
         bool(done) and "25845.00" in (done[0] / "enrollment_report.txt").read_text(encoding="utf-8"))
    r.actual = f"Exit code {code}; completed runs: {len(done)}; source_line by enrollment: {lines_found}."
    return r


def test_blank_line_error_location():
    r = Result("A8", "Error location is correct when the file has a blank line",
               f"Blank line inserted after E-1001 in {FILE_1}, and the course of E-1003 changed to Italian "
               "(E-1003 is on file line 5).",
               "Failure that names line 5, the real line in the file.")
    inp, out = new_case("A8_blank_line_invalid")
    copy_raw(inp)
    insert_blank_line_after_first_row(inp / FILE_1)
    edit_file(inp / FILE_1, "E-1003,Ana Costa,French", "E-1003,Ana Costa,Italian")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_1, "Italian", "line(s) [5]"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_semicolon_file():
    r = Result("A9", "Semicolon-separated file",
               f"{FILE_2} saved with semicolons instead of commas (the default of Excel in some regions).",
               "Failure that tells the user to save a comma-separated UTF-8 CSV; no completed outputs.")
    inp, out = new_case("A9_semicolon_file")
    copy_raw(inp)
    path = inp / FILE_2
    path.write_text(path.read_text(encoding="utf-8").replace(",", ";"), encoding="utf-8")
    code, text = run(inp, out)
    message, _ = failed_run_checks(r, out, code, text, [FILE_2, "semicolon-separated", "comma-separated"])
    r.actual = f"Exit code {code}; no completed run; error logged: \"{message}\"."
    return r


def test_unexpected_error():
    r = Result("A10", "Unexpected error (program defect)",
               "A defect is simulated: build_course_summary raises RuntimeError after the data was validated.",
               "The error is not hidden: it is logged with its traceback, re-raised, and the run is "
               "filed under output/failed; nothing is filed as completed.")
    inp, out = new_case("A10_unexpected_error")
    copy_raw(inp)
    original = run_report.build_course_summary

    def broken(*args, **kwargs):
        raise RuntimeError("simulated defect")
    run_report.build_course_summary = broken
    try:
        code, text = run(inp, out)
    finally:
        run_report.build_course_summary = original

    done, failed = run_folders(out, "completed"), run_folders(out, "failed")
    r.ok("error was re-raised (not swallowed)", code == 2 and "UNEXPECTED ERROR" in text)
    r.ok("no completed run, one failed run", len(done) == 0 and len(failed) == 1)
    log = (failed[0] / "run.log").read_text(encoding="utf-8") if failed else ""
    r.ok("log has FAILED: unexpected error and the traceback",
         "FAILED: unexpected error" in log and "RuntimeError: simulated defect" in log)
    history = pd.read_csv(out / "run_history.csv")
    r.ok("history says FAILED with the reason",
         history["status"].iloc[-1] == "FAILED" and "unexpected error" in str(history["message"].iloc[-1]))
    if failed:
        r.evidence = rel(failed[0] / "run.log")
    r.actual = (f"Error re-raised (harness code {code}); completed runs: {len(done)}; failed runs: {len(failed)}; "
                "log contains 'RuntimeError: simulated defect' with traceback; history row FAILED.")
    return r


# ---------- RECORD ----------

def write_record(required, additional):
    all_results = required + additional
    passed = sum(1 for r in all_results if r.passed)
    lines = [
        "# ST4 Test Record",
        "## Global Languages Academy - Batch Enrollment Report",
        "",
        "**Students:** Bryan Strey, Victor Luis Soares Brito",
        "",
        f"**Executed:** {datetime.now():%Y-%m-%d %H:%M:%S} | Python {platform.python_version()} | "
        f"pandas {pd.__version__} | {platform.system()}",
        "",
        "**How to reproduce:** `python tests/run_tests.py` from the project root. "
        "This file is regenerated by that command.",
        "",
        f"**Result: {passed} of {len(all_results)} tests passed** "
        f"({sum(1 for r in required if r.passed)} of {len(required)} required, "
        f"{sum(1 for r in additional if r.passed)} of {len(additional)} additional).",
        "",
        "| ID | Test condition | Result |",
        "|---|---|---|",
    ]
    for r in all_results:
        lines.append(f"| {r.test_id} | {r.condition} | {'PASS' if r.passed else 'FAIL'} |")

    lines += [
        "", "---", "",
        "## Independent check (hand calculation)", "",
        "These expected values were calculated manually from the business rules, without using the "
        "program's functions, before the program was run. They are typed into `tests/run_tests.py` "
        "as constants. "
        "Semester total = tuition x 6 + enrollment fee (USD 150.00, waived on renewal).", "",
        "| Enrollment | Course and base price | Discounts | Monthly tuition | Fee | Semester total |",
        "|---|---|---|---|---|---|",
    ]
    for eid, course, discounts, tuition, fee, total in HAND_CALCULATION:
        lines.append(f"| {eid} | {course} | {discounts} | {tuition:.2f} | {fee:.2f} | {total:.2f} |")
    lines += [
        "",
        f"Batch totals: projected semester revenue **{EXPECTED_REVENUE:.2f}**; discounts granted "
        f"**{EXPECTED_DISCOUNTS:.2f}** (tuition discounts x 6 months, 8.2% of list tuition 27000.00). "
        "By course: English 4 enrollments 10035.00; French 3 enrollments 8076.00; "
        "Spanish 3 enrollments 7734.00.",
        "",
        "---", "",
        "## Required tests (ST4)", "",
    ]

    def block(r):
        out = [
            f"### {r.test_id} - {r.condition}", "",
            "| Field | Record |", "|---|---|",
            f"| Input / setup | {r.setup} |",
            f"| Expected result | {r.expected} |",
            f"| Actual result | {r.actual} |",
            f"| Pass / fail | **{'PASS' if r.passed else 'FAIL'}** |",
            f"| Evidence | `{r.evidence}` |",
            "",
            "Checks performed: " + "; ".join(
                f"{d} ({'ok' if ok else 'FAILED'})" for d, ok in r.checks) + ".",
            "",
        ]
        return out

    for r in required:
        lines += block(r)
    lines += ["---", "", "## Additional tests", ""]
    for r in additional:
        lines += block(r)
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text("\n".join(lines), encoding="utf-8")


def main():
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    required = [test_valid_batch(), test_invalid_rule_value(), test_missing_column(),
                test_no_matching_files(), test_second_run()]
    additional = [test_duplicate_key(), test_blank_name(), test_invalid_yes_no(),
                  test_missing_folder(), test_header_only_file(), test_write_failure(),
                  test_blank_line_traceability(), test_blank_line_error_location(),
                  test_semicolon_file(), test_unexpected_error()]
    for r in required + additional:
        print(f"{r.test_id} {'PASS' if r.passed else 'FAIL'}  {r.condition}")
        for problem in r.failing():
            print(f"      failed check: {problem}")
    write_record(required, additional)
    print(f"\nRecord written to {RECORD.relative_to(PROJECT).as_posix()}")
    return 0 if all(r.passed for r in required + additional) else 1


if __name__ == "__main__":
    sys.exit(main())
