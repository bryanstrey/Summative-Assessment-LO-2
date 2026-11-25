# =========================================================
# run_report.py - Global Languages Academy: batch enrollment report (ST4)
# =========================================================
# One run command:   python run_report.py
#
# What one run does:
#   1. selects every file named enrollments_*.csv in data/raw/st4/
#   2. reads and validates ALL files (one invalid file stops the whole batch)
#   3. applies the school's pricing and discount rules (school_rules.py)
#   4. writes processed CSVs, an Excel workbook and a text report
#   5. checks that CSVs and workbook add up to the same totals
#   6. writes a log and files the run under output/completed or output/failed
#
# Raw files are only read, never changed.
# =========================================================

import argparse
import csv
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill

import school_rules as rules
from validation import validate_file, validate_batch

# ---------- CONFIGURATION ----------
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = BASE_DIR / "data" / "raw" / "st4"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
FILE_PATTERN = "enrollments_*.csv"
LOGGER_NAME = "language_school"

MONEY_FORMAT = '"USD "#,##0.00'
MONEY_COLUMNS = {
    "base_tuition", "final_tuition", "enrollment_fee", "semester_total",
    "list_tuition", "discount_amount", "semester_revenue",
}
PERCENT_COLUMNS = {"discount_pct"}
COLUMN_WIDTHS = {
    "student_name": 22, "source_file": 28, "discount_level": 18,
    "enrollment_id": 15, "course": 12, "item": 28, "value": 80,
}
FONT_NAME = "Arial"
WORKBOOK_SHEETS = ["Enrollments", "By_Course", "Run_Info"]
PROCESSED_COLUMNS = [
    "enrollment_id", "student_name", "course", "sibling_enrolled",
    "payment_method", "renewal", "coupon_code", "base_tuition",
    "discount_pct", "discount_level", "final_tuition", "enrollment_fee",
    "semester_total", "list_tuition", "discount_amount",
    "source_file", "source_line",
]


# ---------- HELPER ----------

def show_path(path):
    """Show a path relative to the project folder when possible."""
    try:
        return Path(path).resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


# ---------- STEP 1: SELECT FILES ----------

def select_input_files(input_dir, pattern=FILE_PATTERN):
    """Selection rule: every file matching the pattern in the input folder."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder not found: {show_path(input_dir)}")
    files = [path for path in sorted(input_dir.glob(pattern)) if path.is_file()]
    if not files:
        raise FileNotFoundError(f"No files matching '{pattern}' in {show_path(input_dir)}")
    return files


# ---------- STEP 2: READ AND VALIDATE ----------

def read_csv_as_text(path):
    """Read every value as text so validation sees exactly what the file contains.

    Blank lines are read as rows of empty text and then dropped, but the row
    index is kept: index + 2 is therefore always the real line number in the
    file (header = line 1), even when the file contains blank lines.
    """
    try:
        data = pd.read_csv(path, dtype=str, keep_default_na=False,
                           encoding="utf-8-sig", skip_blank_lines=False)
        return data[~data.eq("").all(axis=1)]
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise ValueError(f"{path.name}: cannot be read as a comma-separated CSV ({error})") from error


def load_batch(files, logger):
    """Read, validate and stack all files. Any invalid file stops the batch."""
    frames = []
    for path in files:
        logger.info("Reading %s", path.name)
        data = validate_file(read_csv_as_text(path), path.name)
        data["source_file"] = path.name
        data["source_line"] = data.index + 2
        logger.info("Validated %s: %s rows", path.name, len(data))
        frames.append(data)
    batch = pd.concat(frames, ignore_index=True)
    validate_batch(batch)
    logger.info("Validated batch: %s files, %s enrollments", len(files), len(batch))
    return batch


# ---------- STEP 3: APPLY BUSINESS RULES ----------

def process_enrollments(batch, logger):
    """Add price, discount, tuition, fee and totals using the ST2 rule functions."""
    values = {name: [] for name in (
        "base_tuition", "discount_pct", "discount_level", "final_tuition",
        "enrollment_fee", "semester_total", "list_tuition", "discount_amount")}

    for row in batch.itertuples(index=False):
        base = rules.get_course_price(row.course, rules.COURSE_PRICES)
        discount = round(rules.calculate_total_discount(
            row.sibling_enrolled == "yes", row.payment_method == "upfront",
            row.coupon_code), 2)
        tuition = round(rules.calculate_final_tuition(base, discount), 2)
        fee = rules.calculate_enrollment_fee(row.renewal == "yes")

        if row.coupon_code != "" and not rules.is_recognized_coupon(row.coupon_code):
            logger.warning(
                "Unrecognized coupon '%s' (%s, %s line %s): no discount applied",
                row.coupon_code, row.enrollment_id, row.source_file, row.source_line)

        values["base_tuition"].append(base)
        values["discount_pct"].append(discount)
        values["discount_level"].append(rules.classify_discount(discount))
        values["final_tuition"].append(tuition)
        values["enrollment_fee"].append(fee)
        values["semester_total"].append(round(rules.calculate_semester_total(tuition, fee), 2))
        values["list_tuition"].append(round(base * rules.SEMESTER_MONTHS, 2))
        values["discount_amount"].append(round((base - tuition) * rules.SEMESTER_MONTHS, 2))

    processed = batch.copy()
    for name, column in values.items():
        processed[name] = column
    return processed[PROCESSED_COLUMNS]


def build_course_summary(processed):
    """Summary by course, sorted by projected revenue (highest first)."""
    summary = processed.groupby("course", as_index=False).agg(
        enrollments=("enrollment_id", "count"),
        list_tuition=("list_tuition", "sum"),
        discount_amount=("discount_amount", "sum"),
        semester_revenue=("semester_total", "sum"),
    )
    summary = summary.sort_values(
        ["semester_revenue", "course"], ascending=[False, True]).reset_index(drop=True)
    return summary.round(2)


# ---------- STEP 4: WRITE OUTPUTS ----------

def write_processed_csvs(processed, processed_dir):
    """One processed CSV per source file; mode 'x' refuses to overwrite."""
    processed_dir.mkdir(parents=True)
    paths = []
    for source_file, part in processed.groupby("source_file", sort=True):
        destination = processed_dir / f"{Path(source_file).stem}_processed.csv"
        part.to_csv(destination, index=False, mode="x", encoding="utf-8", float_format="%.2f")
        paths.append(destination)
    return paths


def format_sheet(ws):
    """Same look on every sheet: header style, widths, formats, freeze, filter."""
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(name=FONT_NAME, bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="205A6B")
    for column in ws.columns:
        header = column[0].value
        ws.column_dimensions[column[0].column_letter].width = COLUMN_WIDTHS.get(header, 18)
        for cell in column[1:]:
            cell.font = Font(name=FONT_NAME)
            if header in MONEY_COLUMNS:
                cell.number_format = MONEY_FORMAT
            elif header in PERCENT_COLUMNS:
                cell.number_format = "0%"


def build_run_info(processed, run_id, generated):
    """Traceability sheet: which run, which files, which units and rounding."""
    items = [
        ("Run ID", run_id),
        ("Generated", f"{generated:%Y-%m-%d %H:%M:%S}"),
        ("Source files", ", ".join(sorted(processed["source_file"].unique()))),
        ("Currency", "USD"),
        ("Semester length (months)", str(rules.SEMESTER_MONTHS)),
        ("Rounding", "Money values are rounded to cents; discount_pct is a fraction (0.20 = 20%)"),
        ("Business rules", "Same rules as the ST2 project; see README.md"),
    ]
    return pd.DataFrame(items, columns=["item", "value"])


def write_workbook(processed, by_course, run_info, path):
    """Excel workbook: detailed records, business summary and run information."""
    with path.open("xb") as target:
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            processed.to_excel(writer, sheet_name="Enrollments", index=False)
            by_course.to_excel(writer, sheet_name="By_Course", index=False)
            run_info.to_excel(writer, sheet_name="Run_Info", index=False)
            for sheet in writer.sheets.values():
                format_sheet(sheet)


def check(condition, message):
    if not condition:
        raise ValueError(f"Output verification failed: {message}")


def verify_outputs(processed, csv_paths, workbook_path):
    """Read the saved files back and compare them with the validated data."""
    rows = len(processed)
    total = round(processed["semester_total"].sum(), 2)

    csv_data = pd.concat([pd.read_csv(path) for path in csv_paths], ignore_index=True)
    check(len(csv_data) == rows, f"CSV rows {len(csv_data)} != {rows}")
    check(round(csv_data["semester_total"].sum(), 2) == total, "CSV total differs")

    sheets = pd.read_excel(workbook_path, sheet_name=None, engine="openpyxl")
    check(list(sheets) == WORKBOOK_SHEETS, f"unexpected sheets {list(sheets)}")
    detail, summary = sheets["Enrollments"], sheets["By_Course"]
    check(len(detail) == rows, f"workbook rows {len(detail)} != {rows}")
    check(round(detail["semester_total"].sum(), 2) == total, "workbook detail total differs")
    check(detail["source_file"].nunique() == processed["source_file"].nunique(),
          "workbook source files differ")
    check(int(summary["enrollments"].sum()) == rows, "summary enrollments differ")
    check(round(summary["semester_revenue"].sum(), 2) == total, "summary revenue differs")
    return {"rows": rows, "total": total}


# ---------- STEP 5: REPORT ----------

def calculate_indicators(processed, by_course):
    """Business indicators, calculated only from the validated data."""
    enrollments = len(processed)
    revenue = round(processed["semester_total"].sum(), 2)
    discounts = round(processed["discount_amount"].sum(), 2)
    list_total = processed["list_tuition"].sum()
    high = int((processed["discount_level"] == "High discount").sum())
    top = by_course.iloc[0]
    unrecognized = int(sum(
        1 for code in processed["coupon_code"]
        if code != "" and not rules.is_recognized_coupon(code)))
    return {
        "enrollments": enrollments,
        "revenue": revenue,
        "discounts": discounts,
        "discount_share": discounts / list_total * 100,
        "high_count": high,
        "high_share": high / enrollments * 100,
        "renewals": int((processed["renewal"] == "yes").sum()),
        "top_course": top["course"],
        "top_revenue": float(top["semester_revenue"]),
        "top_share": float(top["semester_revenue"]) / revenue * 100,
        "unrecognized_coupons": unrecognized,
    }


def make_report_text(processed, by_course, run_id, generated, input_dir):
    """Short text report: evidence first, then interpretation and limitation."""
    ind = calculate_indicators(processed, by_course)
    counts = processed.groupby("source_file").size()
    source_lines = [f"  - {name} ({count} enrollments)" for name, count in counts.items()]

    unknown = ind["unrecognized_coupons"]
    if unknown > 0:
        verb = "was" if unknown == 1 else "were"
        noun = "coupon code" if unknown == 1 else "coupon codes"
        coupon_note = (f"- {unknown} {noun} {verb} not recognized and received no discount;\n"
                       "  check the source files (see run.log).")
    else:
        coupon_note = "- All coupon codes were recognized or blank."

    lines = [
        "Global Languages Academy - Enrollment Batch Report",
        "==================================================",
        f"Run: {run_id}",
        "Status: COMPLETED",
        f"Generated: {generated:%Y-%m-%d %H:%M:%S}",
        "",
        "SCOPE",
        f"Selection rule: files named {FILE_PATTERN} in {show_path(input_dir)}",
        f"Source files ({len(counts)}):",
        *source_lines,
        "Amounts are projected values for one 6-month semester, in USD.",
        "",
        "INDICATORS (calculated from the validated data)",
        f"Enrollments: {ind['enrollments']}",
        f"Projected semester revenue (USD): {ind['revenue']:.2f}",
        f"Discounts granted (USD): {ind['discounts']:.2f} "
        f"({ind['discount_share']:.1f}% of list tuition)",
        f"High-discount enrollments: {ind['high_count']} of {ind['enrollments']} "
        f"({ind['high_share']:.1f}%)",
        f"Renewals (enrollment fee waived): {ind['renewals']} of {ind['enrollments']}",
        f"Top course by projected revenue: {ind['top_course']} "
        f"(USD {ind['top_revenue']:.2f}, {ind['top_share']:.1f}% of total)",
        "",
        "FINDING (interpretation, not a calculated value)",
        f"{ind['high_count']} of {ind['enrollments']} enrollments received a High discount "
        "(more than 10%),",
        f"and discounts reduced list tuition by {ind['discount_share']:.1f}%.",
        "Because discounts stack, the school may want to confirm that combining sibling,",
        "upfront and coupon discounts is intended. This report measures the discounts; it",
        "does not say whether they were appropriate.",
        "",
        "LIMITATIONS",
        f"- Results cover only the {len(counts)} selected files; enrollments that were not",
        "  exported to the input folder are not represented.",
        "- Amounts are projections under the school's rules, not payments received.",
        coupon_note,
    ]
    return "\n".join(lines) + "\n"


def write_report(text, work_dir):
    """Write a draft first; the final name appears only after a complete write."""
    draft = work_dir / "enrollment_report.tmp"
    final = work_dir / "enrollment_report.txt"
    with draft.open("x", encoding="utf-8") as file:
        file.write(text)
    draft.replace(final)
    return final


# ---------- LOGGING AND RUN BOOKKEEPING ----------

def start_log(work_dir):
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(work_dir / "run.log", mode="x", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def close_log(logger):
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def file_the_run(work_dir, output_dir, run_id, status):
    """Move the run folder to output/completed or output/failed."""
    destination = output_dir / ("completed" if status == "COMPLETED" else "failed") / run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(work_dir), str(destination))
    return destination


def relative_folder(folder, output_dir):
    """Folder as text relative to the output folder (portable between computers)."""
    try:
        return Path(folder).relative_to(output_dir).as_posix()
    except ValueError:
        return str(folder)


def append_run_history(output_dir, row):
    """One line per run, so the last line is always the latest run and its status."""
    history = output_dir / "run_history.csv"
    is_new = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if is_new:
            writer.writerow(["run_id", "finished_at", "status", "source_files",
                             "enrollments", "message", "run_folder"])
        writer.writerow(row)


# ---------- MAIN WORKFLOW ----------

def main(input_dir=DEFAULT_INPUT_DIR, output_dir=DEFAULT_OUTPUT_DIR):
    """Run the whole batch. Returns 0 if completed, 1 if the run failed."""
    started = datetime.now()
    run_id = started.strftime("%Y%m%d_%H%M%S_%f")
    work_dir = output_dir / "in_progress" / run_id

    try:
        work_dir.mkdir(parents=True, exist_ok=False)
        logger = start_log(work_dir)
    except OSError as error:
        print(f"Startup error: run folder or log could not be created ({error}).")
        return 1

    logger.info("STARTED run=%s", run_id)
    logger.info("Input folder: %s | pattern: %s", show_path(input_dir), FILE_PATTERN)
    status, message, file_count, enrollment_count = "FAILED", "", 0, 0

    try:
        files = select_input_files(input_dir)
        file_count = len(files)
        logger.info("Selected %s file(s): %s", file_count, ", ".join(p.name for p in files))

        batch = load_batch(files, logger)
        processed = process_enrollments(batch, logger)
        enrollment_count = len(processed)
        by_course = build_course_summary(processed)

        csv_paths = write_processed_csvs(processed, work_dir / "processed")
        logger.info("Wrote %s processed CSV file(s)", len(csv_paths))
        workbook_path = work_dir / "enrollment_workbook.xlsx"
        run_info = build_run_info(processed, run_id, started)
        write_workbook(processed, by_course, run_info, workbook_path)
        logger.info("Wrote workbook %s", workbook_path.name)

        verified = verify_outputs(processed, csv_paths, workbook_path)
        logger.info("Verified CSVs and workbook: rows=%s total=%.2f",
                    verified["rows"], verified["total"])

        report = make_report_text(processed, by_course, run_id, datetime.now(), input_dir)
        write_report(report, work_dir)
        logger.info("Wrote report enrollment_report.txt")
        logger.info("COMPLETED run=%s enrollments=%s revenue=%.2f",
                    run_id, enrollment_count, verified["total"])
        status = "COMPLETED"

    except (OSError, ValueError) as error:       # known failures: files and data
        message = str(error)
        logger.error("FAILED: %s", error)
    except Exception as error:                    # unexpected: record and re-raise
        message = f"unexpected error: {error!r}"
        logger.exception("FAILED: unexpected error")
        raise
    finally:
        close_log(logger)
        try:
            final_dir = file_the_run(work_dir, output_dir, run_id, status)
        except OSError as error:
            status, final_dir = "FAILED", work_dir
            message = f"{message} | run folder could not be filed: {error}".strip(" |")
        try:
            append_run_history(output_dir, [
                run_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status,
                file_count, enrollment_count, message, relative_folder(final_dir, output_dir)])
        except OSError as error:
            print(f"Warning: run history could not be updated ({error}).")

    if status == "COMPLETED":
        print(f"Run {run_id} COMPLETED: {enrollment_count} enrollments from {file_count} file(s).")
        print(f"Outputs: {show_path(final_dir)}")
        return 0
    print(f"Run {run_id} FAILED: {message}")
    print(f"Details: {show_path(final_dir / 'run.log')}")
    return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Batch enrollment report for Global Languages Academy.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
                        help="folder with enrollments_*.csv (default: data/raw/st4)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="folder for run results (default: output)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse_args()
    sys.exit(main(arguments.input_dir, arguments.output_dir))
