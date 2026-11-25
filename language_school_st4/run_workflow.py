# =========================================================
# run_workflow.py - Global Languages Academy: enrollments + exchange rates (ST5)
# =========================================================
# One documented command (from the project folder):
#
#     python run_workflow.py --mode fixture      # synthetic demonstration data (default, no internet)
#     python run_workflow.py --mode live         # ask the API now, validate, save the answer
#     python run_workflow.py --mode saved        # reuse the latest saved real answer
#   (--source-mode is accepted as the same option). A failed mode is never replaced
#   by another mode automatically.
#
# Business question: what is the projected semester revenue of the enrolled
# students in Brazilian reais (BRL), using the USD->BRL rate of the enrollment date?
#
# What one run does:
#   1. reads and validates the enrollment files and applies the school's rules (ST4 code)
#   2. gets exchange rates: live from the API (validated, then saved in
#      data/external/), from a saved response (checksum verified) or from the
#      synthetic fixture in data/fixtures/ (clearly labeled, not market data)
#   3. joins enrollments and rates by date and checks the join
#   4. writes one integrated CSV, one Excel workbook and one report
#   5. verifies the written files, writes a log and files the run under
#      <output>/completed/ or <output>/failed/
#
# ST4 files (run_report.py, school_rules.py, validation.py) are imported, not changed.
# Results go to output/st5/ by default, so ST4 results are never touched.
# =========================================================

import argparse
import csv
import platform
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill

import exchange_api as api
import integration
import run_report as st4

# ---------- CONFIGURATION ----------
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = st4.DEFAULT_INPUT_DIR
DEFAULT_OUTPUT_DIR = BASE_DIR / "output" / "st5"
DEFAULT_EXTERNAL_DIR = BASE_DIR / "data" / "external"
DEFAULT_FIXTURE_DIR = BASE_DIR / "data" / "fixtures"
SOURCE_MODES = ("fixture", "live", "saved")
MODE_MEANING = {
    "live": "bytes returned by the real service in this run",
    "saved": "bytes preserved from an earlier real response (checksum verified)",
    "fixture": "SYNTHETIC invented data for demonstration/testing - not market rates",
}

USD_COLUMNS = {"base_tuition", "final_tuition", "enrollment_fee", "semester_total",
               "list_tuition", "discount_amount", "semester_revenue_usd"}
BRL_COLUMNS = {"final_tuition_brl", "semester_total_brl", "discount_amount_brl",
               "semester_revenue_brl"}
RATE_COLUMNS = {"fx_rate"}
INTEGRATED_COLUMNS = st4.PROCESSED_COLUMNS + [
    "enrollment_date", "fx_rate_date", "fx_rate", "rate_match",
    "final_tuition_brl", "semester_total_brl", "discount_amount_brl"]
WORKBOOK_SHEETS = ["Enrollments", "By_Course", "Exchange_Rates", "Run_Info"]
HISTORY_HEADER = ["run_id", "finished_at", "status", "source_mode", "rates_file",
                  "enrollments", "message", "run_folder"]


# ---------- STEP 1: ENROLLMENTS (reuses the ST4 functions) ----------

def prepare_enrollments(input_dir, logger):
    files = st4.select_input_files(input_dir)
    logger.info("Selected %s file(s): %s", len(files), ", ".join(p.name for p in files))
    batch = st4.load_batch(files, logger)
    processed = st4.process_enrollments(batch, logger)
    return files, integration.add_join_key(processed)


# ---------- STEP 2: EXCHANGE RATES ----------

def request_window(enrollments):
    """Dates to ask for: a few days earlier than the first enrollment, so that a
    weekend or holiday still finds the previous published rate."""
    first = enrollments["enrollment_date"].min().date()
    last = enrollments["enrollment_date"].max().date()
    return first - timedelta(days=integration.MAX_RATE_AGE_DAYS + 2), last


def acquire_live(enrollments, external_dir, api_base_url, timeout, logger):
    start, end = request_window(enrollments)
    logger.info("Live request: %s %s -> %s", api_base_url, start, end)
    fetched = api.fetch_rates(start, end, api_base_url=api_base_url, timeout=timeout,
                              log=logger.warning)
    logger.info("HTTP %s, %s bytes", fetched["http_status"], len(fetched["content"]))
    payload = api.parse_json(fetched["content"], "Exchange-rate API")
    structure = api.inspect_json(payload)
    logger.info("JSON structure: %s", structure)
    rates = api.validate_rates(api.rates_to_dataframe(payload))
    coverage = api.describe_coverage(rates)
    metadata = api.build_metadata(fetched, coverage, structure)
    data_path, _ = api.save_response(fetched["content"], metadata, external_dir)   # only after validation
    logger.info("Saved response %s (+ metadata)", data_path.name)
    return rates, metadata, data_path


def acquire_saved(folder, rates_file, logger, empty_hint):
    """Saved snapshot or fixture: same loader, different folder and label."""
    if rates_file is None:
        saved = api.list_saved_responses(folder)
        if not saved:
            raise api.ExchangeRateError(f"No saved response in {st4.show_path(folder)}. {empty_hint}")
        rates_file = saved[-1]
    content, metadata = api.load_saved_response(rates_file)
    logger.info("Using %s (acquired %s)", rates_file.name, metadata["acquired_at"])
    payload = api.parse_json(content, rates_file.name)
    logger.info("JSON structure: %s", api.inspect_json(payload))
    rates = api.validate_rates(api.rates_to_dataframe(payload))
    return rates, metadata, rates_file


def snapshot_sources(work_dir, files, rates_path):
    """Keep the exact inputs of this run with the run (traceability, ST5_3 slides)."""
    folder = work_dir / "source_snapshot"
    folder.mkdir()
    for path in [*files, rates_path, rates_path.with_name(rates_path.stem + ".metadata.json")]:
        shutil.copyfile(path, folder / path.name)
    return folder


# ---------- STEP 3 and 4: JOIN AND OUTPUTS ----------

def integrate(enrollments, rates, work_dir, logger):
    joined = integration.attach_rates(enrollments, rates)
    try:
        integration.check_integration(enrollments, joined)
    except integration.IntegrationError as error:
        if error.unmatched is not None:
            path = work_dir / "unmatched_enrollments.csv"
            error.unmatched.drop(columns=["fx_rate", "fx_rate_date"], errors="ignore") \
                .to_csv(path, index=False, mode="x", encoding="utf-8")
            logger.error("Enrollments without a rate listed in %s", path.name)
        raise
    converted = integration.add_brl_amounts(joined)
    integration.check_conversion(converted)
    late = int((converted["rate_match"] == integration.MATCH_PREVIOUS).sum())
    if late:
        logger.warning("%s enrollment(s) used the previous published rate", late)
    return converted


def for_output(converted):
    """Integrated table with dates as text and the agreed column order."""
    table = converted.copy()
    for column in ("enrollment_date", "fx_rate_date"):
        table[column] = table[column].dt.strftime("%Y-%m-%d")
    return table[INTEGRATED_COLUMNS]


def build_run_info(run_id, generated, source_mode, rates_path, metadata, files, business_period):
    parameters = ", ".join(f"{k}={v}" for k, v in metadata["parameters"].items())
    items = [
        ("Run ID", run_id),
        ("Generated", f"{generated:%Y-%m-%d %H:%M:%S}"),
        ("Source mode", source_mode),
        ("Source mode meaning", MODE_MEANING[source_mode]),
        ("Business period", business_period),
        ("Rates file", rates_path.name),
        ("Provider", metadata["provider"]),
        ("Endpoint", metadata["endpoint"]),
        ("Parameters", parameters),
        ("Acquired at (UTC)", metadata["acquired_at"]),
        ("Rate units", metadata["units"]),
        ("Rates in response", f"{metadata['rates_count']} ({metadata['first_rate_date']} to {metadata['last_rate_date']})"),
        ("Response SHA-256", metadata["response_sha256"]),
        ("Use conditions", metadata["use_conditions"]),
        ("Enrollment files", ", ".join(p.name for p in files)),
        ("Rate matching", f"same day, else latest earlier rate within {integration.MAX_RATE_AGE_DAYS} days"),
        ("Rounding", "USD values rounded to cents (ST4); BRL = USD x rate, rounded to centavos per row"),
        ("Environment", f"Python {platform.python_version()}, pandas {pd.__version__}, requests {api.requests.__version__}"),
    ]
    return pd.DataFrame(items, columns=["item", "value"])


def format_sheet(ws):
    """Same look as the ST4 workbook, plus BRL and rate formats."""
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(name=st4.FONT_NAME, bold=True, color="FFFFFF")
        cell.fill = PatternFill(fill_type="solid", fgColor="205A6B")
    for column in ws.columns:
        header = column[0].value
        ws.column_dimensions[column[0].column_letter].width = st4.COLUMN_WIDTHS.get(header, 18)
        for cell in column[1:]:
            cell.font = Font(name=st4.FONT_NAME)
            if header in USD_COLUMNS:
                cell.number_format = '"USD "#,##0.00'
            elif header in BRL_COLUMNS:
                cell.number_format = '"BRL "#,##0.00'
            elif header in RATE_COLUMNS:
                cell.number_format = "0.0000"
            elif header in st4.PERCENT_COLUMNS:
                cell.number_format = "0%"


def write_integrated_csv(table, work_dir):
    path = work_dir / "integrated_enrollments.csv"
    # float_format="%.2f" is right for money but would cut the rate to 2 decimals
    # (5.0277 -> 5.03), so the rate is written as text with 4 decimals (PTAX precision).
    table = table.assign(fx_rate=table["fx_rate"].map("{:.4f}".format))
    table.to_csv(path, index=False, mode="x", encoding="utf-8", float_format="%.2f")
    return path


def write_workbook(table, by_course, usage, run_info, path):
    with path.open("xb") as target:
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            table.to_excel(writer, sheet_name="Enrollments", index=False)
            by_course.to_excel(writer, sheet_name="By_Course", index=False)
            usage.to_excel(writer, sheet_name="Exchange_Rates", index=False)
            run_info.to_excel(writer, sheet_name="Run_Info", index=False)
            for sheet in writer.sheets.values():
                format_sheet(sheet)


def verify_outputs(converted, csv_path, workbook_path):
    """Read the written files back and compare them with the integrated data."""
    rows = len(converted)
    usd = round(converted["semester_total"].sum(), 2)
    brl = round(converted["semester_total_brl"].sum(), 2)

    csv_data = pd.read_csv(csv_path)
    st4.check(len(csv_data) == rows, f"CSV rows {len(csv_data)} != {rows}")
    st4.check(round(csv_data["semester_total"].sum(), 2) == usd, "CSV USD total differs")
    st4.check(round(csv_data["semester_total_brl"].sum(), 2) == brl, "CSV BRL total differs")
    st4.check(not csv_data["fx_rate"].isna().any(), "CSV has rows without a rate")
    st4.check((csv_data["fx_rate"] - converted["fx_rate"].values).abs().max() < 0.00005,
              "CSV rate differs from the rate used")

    sheets = pd.read_excel(workbook_path, sheet_name=None, engine="openpyxl")
    st4.check(list(sheets) == WORKBOOK_SHEETS, f"unexpected sheets {list(sheets)}")
    detail, summary, rates = sheets["Enrollments"], sheets["By_Course"], sheets["Exchange_Rates"]
    st4.check(len(detail) == rows, f"workbook rows {len(detail)} != {rows}")
    st4.check(round(detail["semester_total_brl"].sum(), 2) == brl, "workbook BRL total differs")
    st4.check(round(summary["semester_revenue_usd"].sum(), 2) == usd, "summary USD differs")
    st4.check(round(summary["semester_revenue_brl"].sum(), 2) == brl, "summary BRL differs")
    st4.check(int(rates["enrollments"].sum()) == rows, "rate sheet enrollments differ")
    st4.check(round(rates["semester_revenue_brl"].sum(), 2) == brl, "rate sheet BRL differs")
    return {"rows": rows, "usd": usd, "brl": brl}


# ---------- STEP 5: REPORT ----------

def make_report_text(converted, by_course, usage, run_id, generated, source_mode,
                     rates_path, metadata, files, business_period):
    ind = st4.calculate_indicators(converted, st4.build_course_summary(converted))
    usd, brl = ind["revenue"], round(converted["semester_total_brl"].sum(), 2)
    previous = int((converted["rate_match"] == integration.MATCH_PREVIOUS).sum())
    rate_lines = [
        f"  - enrollments of {row.enrollment_date}: rate {row.fx_rate:.4f} "
        f"(published {row.fx_rate_date}, {row.rate_match.replace('_', ' ')}) "
        f"-> {row.enrollments} enrollments, USD {row.semester_revenue_usd:.2f} = "
        f"BRL {row.semester_revenue_brl:.2f}"
        for row in usage.itertuples()]
    course_lines = [
        f"  - {row.course}: {row.enrollments} enrollments, USD {row.semester_revenue_usd:.2f}"
        f" = BRL {row.semester_revenue_brl:.2f}"
        for row in by_course.itertuples()]
    lines = [
        "Global Languages Academy - Enrollments with Exchange Rates (ST5)",
        "================================================================",
        f"Run: {run_id}",
        "Status: COMPLETED",
        f"Generated: {generated:%Y-%m-%d %H:%M:%S}",
        f"SOURCE MODE: {source_mode.upper()}  - {MODE_MEANING[source_mode]}",
        f"Rates file: {rates_path.name}",
        f"Business period (enrollment dates): {business_period}",
        *(["*** SYNTHETIC DEMONSTRATION: the rates are invented and the amounts in BRL are NOT real. ***"]
          if source_mode == "fixture" else []),
        "",
        "EXTERNAL INFORMATION USED",
        f"Provider: {metadata['provider']}",
        f"Endpoint: {metadata['endpoint']}",
        "Parameters: " + ", ".join(f"{k}={v}" for k, v in metadata["parameters"].items()),
        f"Acquired at (UTC): {metadata['acquired_at']}",
        f"Units: {metadata['units']} (USD is the school's price currency)",
        f"Rates in response: {metadata['rates_count']} "
        f"({metadata['first_rate_date']} to {metadata['last_rate_date']})",
        f"Use conditions: {metadata['use_conditions']}",
        "",
        "INTERNAL DATA",
        f"Enrollment files ({len(files)}): " + ", ".join(p.name for p in files),
        f"Enrollments: {ind['enrollments']}  (unchanged by the join)",
        "",
        "RESULT",
        f"Projected semester revenue: USD {usd:.2f} = BRL {brl:.2f}",
        "By enrollment date:",
        *rate_lines,
        "By course:",
        *course_lines,
        "",
        "CHECKS PASSED",
        "- Row count and USD total identical before and after the join.",
        "- Every enrollment found a rate (same day or latest earlier day within "
        f"{integration.MAX_RATE_AGE_DAYS} days).",
        "- Every BRL value recomputed independently from USD x rate.",
        "- CSV and workbook read back and compared with the integrated data.",
        "",
        "LIMITATIONS",
        "- The conversion is an estimate for budgeting. It is not the rate at which any",
        "  payment was or will be converted, and not an accounting or tax rate.",
        f"- {previous} of {ind['enrollments']} enrollments used the previous published rate "
        "(no rate on their own date)." if previous else
        "- Every enrollment had a rate published on its own date.",
        "- The date of each enrollment is taken from the file name, not from a column.",
        "- Rates can be late or revised by the provider; a saved response is a snapshot.",
        f"- Unrecognized coupons: {ind['unrecognized_coupons']} (no discount applied; see run.log).",
    ]
    return "\n".join(lines) + "\n"


# ---------- HISTORY ----------

def append_history(output_dir, row):
    history = output_dir / "run_history.csv"
    is_new = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if is_new:
            writer.writerow(HISTORY_HEADER)
        writer.writerow(row)


# ---------- MAIN WORKFLOW ----------

def main(input_dir=DEFAULT_INPUT_DIR, output_dir=DEFAULT_OUTPUT_DIR,
         external_dir=DEFAULT_EXTERNAL_DIR, source_mode="saved", rates_file=None,
         api_base_url=api.API_BASE_URL, timeout=api.REQUEST_TIMEOUT,
         fixture_dir=DEFAULT_FIXTURE_DIR):
    """Run the whole workflow. Returns 0 if completed, 1 if the run failed."""
    started = datetime.now()
    run_id = started.strftime("%Y%m%d_%H%M%S_%f")
    work_dir = output_dir / "in_progress" / run_id
    try:
        work_dir.mkdir(parents=True, exist_ok=False)
        logger = st4.start_log(work_dir)
    except OSError as error:
        print(f"Startup error: run folder or log could not be created ({error}).")
        return 1

    logger.info("STARTED run=%s source_mode=%s", run_id, source_mode)
    status, message, enrollment_count, rates_name = "FAILED", "", 0, ""
    try:
        if source_mode not in SOURCE_MODES:
            raise ValueError(f"Unknown source mode '{source_mode}' (use live or saved).")
        files, enrollments = prepare_enrollments(input_dir, logger)
        enrollment_count = len(enrollments)

        if source_mode == "live":
            rates, metadata, rates_path = acquire_live(
                enrollments, external_dir, api_base_url, timeout, logger)
        elif source_mode == "saved":
            rates, metadata, rates_path = acquire_saved(
                external_dir, rates_file, logger, "Run once with --mode live first.")
        else:
            rates, metadata, rates_path = acquire_saved(
                fixture_dir, rates_file, logger, "The synthetic fixture is missing from the project.")
        rates_name = rates_path.name
        period = (f"{enrollments['enrollment_date'].min():%Y-%m-%d} to "
                  f"{enrollments['enrollment_date'].max():%Y-%m-%d}")
        logger.info("Source mode %s | business period %s | rates file %s", source_mode, period, rates_name)

        converted = integrate(enrollments, rates, work_dir, logger)
        table = for_output(converted)
        by_course = integration.summarize_by_course_brl(converted)
        usage = integration.summarize_rate_usage(converted)

        snapshot_sources(work_dir, files, rates_path)
        csv_path = write_integrated_csv(table, work_dir)
        workbook_path = work_dir / "enrollment_workbook_st5.xlsx"
        run_info = build_run_info(run_id, started, source_mode, rates_path, metadata, files, period)
        write_workbook(table, by_course, usage, run_info, workbook_path)
        logger.info("Wrote %s and %s", csv_path.name, workbook_path.name)

        verified = verify_outputs(converted, csv_path, workbook_path)
        logger.info("Verified outputs: rows=%s USD=%.2f BRL=%.2f",
                    verified["rows"], verified["usd"], verified["brl"])

        report = make_report_text(converted, by_course, usage, run_id, datetime.now(),
                                  source_mode, rates_path, metadata, files, period)
        st4.write_report(report, work_dir)
        logger.info("COMPLETED run=%s", run_id)
        status = "COMPLETED"

    except (OSError, ValueError) as error:       # known failures: files, API, data
        message = str(error)
        logger.error("FAILED: %s", error)
    except Exception as error:                    # unexpected: record and re-raise
        message = f"unexpected error: {error!r}"
        logger.exception("FAILED: unexpected error")
        raise
    finally:
        st4.close_log(logger)
        try:
            final_dir = st4.file_the_run(work_dir, output_dir, run_id, status)
        except OSError as error:
            status, final_dir = "FAILED", work_dir
            message = f"{message} | run folder could not be filed: {error}".strip(" |")
        try:
            append_history(output_dir, [
                run_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, source_mode,
                rates_name, enrollment_count, message, st4.relative_folder(final_dir, output_dir)])
        except OSError as error:
            print(f"Warning: run history could not be updated ({error}).")

    if status == "COMPLETED":
        print(f"Run {run_id} COMPLETED ({source_mode} mode): {enrollment_count} enrollments, "
              f"rates from {rates_name}.")
        print(f"Outputs: {st4.show_path(final_dir)}")
        return 0
    print(f"Run {run_id} FAILED ({source_mode} mode): {message}")
    print(f"Details: {st4.show_path(final_dir / 'run.log')}")
    return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Enrollment report in USD and BRL using exchange rates (ST5).")
    parser.add_argument("--mode", "--source-mode", dest="source_mode", choices=SOURCE_MODES,
                        default="fixture",
                        help="fixture = synthetic demonstration data (default); live = call the API "
                             "and save the answer; saved = reuse a saved real answer")
    parser.add_argument("--rates-file", type=Path, default=None,
                        help="saved response to use in saved mode (default: latest in data/external)")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-dir", type=Path, default=DEFAULT_EXTERNAL_DIR)
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--api-base-url", default=api.API_BASE_URL,
                        help="only change for tests (default: the real Frankfurter v2 URL)")
    parser.add_argument("--timeout", type=float, default=None,
                        help="seconds for connect and read (default: 5 connect, 20 read)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    sys.exit(main(a.input_dir, a.output_dir, a.external_dir, a.source_mode,
                  a.rates_file, a.api_base_url, a.timeout or api.REQUEST_TIMEOUT, a.fixture_dir))
