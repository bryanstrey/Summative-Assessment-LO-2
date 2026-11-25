# =========================================================
# tests/run_tests_st5.py - Test record for the ST5 workflow
# =========================================================
# Run from the project root:   python tests/run_tests_st5.py
#
# IMPORTANT - what these tests are and are not:
#   The real exchange-rate API is NOT called. Each test starts a small web
#   server on this computer (127.0.0.1) that answers like the API would, with
#   SYNTHETIC rates invented for the tests (5.2000 and 5.2500 etc. are not real
#   market values). This proves that the code handles good answers and bad
#   answers correctly. It does NOT prove what the real API returns today.
#   The real response must be acquired once with:
#       python run_workflow.py --mode live
#
# Expected values were calculated by hand from the ST4 hand calculation
# (semester totals per student) and the synthetic rates.
# The record is written to docs/st5_test_record.md.
# =========================================================

import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import sys
import threading
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.environ["NO_PROXY"] = "127.0.0.1,localhost"      # local test server must not use the proxy
os.environ["no_proxy"] = "127.0.0.1,localhost"

import exchange_api as api          # noqa: E402
api.RETRY_DELAY_SECONDS = 0                       # tests must not wait between retries
import integration                  # noqa: E402
import run_workflow                 # noqa: E402

RAW = PROJECT / "data" / "raw" / "st4"
SANDBOX = PROJECT / "tests" / "test_runs_st5"
RECORD = PROJECT / "docs" / "st5_test_record.md"
FILE_1, FILE_2 = "enrollments_2026-10-21.csv", "enrollments_2026-10-22.csv"

# Hand-calculated semester totals (USD) per enrollment, from the ST4 test record.
USD_TOTALS = {"E-1001": "2310.00", "E-1002": "2520.00", "E-1003": "2742.00",
              "E-1004": "2715.00", "E-1005": "2544.00", "E-1006": "2736.00",
              "E-1007": "2160.00", "E-1008": "2670.00", "E-1009": "2598.00",
              "E-1010": "2850.00"}
FILE_1_IDS = ["E-1001", "E-1002", "E-1003", "E-1004", "E-1005"]
FILE_2_IDS = ["E-1006", "E-1007", "E-1008", "E-1009", "E-1010"]
SYNTHETIC_RATE = {"2026-10-21": "5.2000", "2026-10-22": "5.2500"}


def hand_brl(ids, rate):
    """USD total x rate per student, rounded half-up to centavos, summed (Decimal)."""
    return sum((Decimal(USD_TOTALS[i]) * Decimal(rate)).quantize(Decimal("0.01"), ROUND_HALF_UP)
               for i in ids)


EXPECTED_BRL = hand_brl(FILE_1_IDS, "5.2000") + hand_brl(FILE_2_IDS, "5.2500")


def rate_item(day, rate, base="USD", quote="BRL"):
    return {"date": day, "base": base, "quote": quote, "rate": rate}


# Synthetic answer: a normal range response. It starts with the latest earlier
# rate (10-14, as the Frankfurter docs describe) and has no weekend entries.
GOOD_RATES = [rate_item("2026-10-14", 5.1000), rate_item("2026-10-15", 5.1100),
              rate_item("2026-10-16", 5.1200), rate_item("2026-10-19", 5.1500),
              rate_item("2026-10-20", 5.1800), rate_item("2026-10-21", 5.2000),
              rate_item("2026-10-22", 5.2500)]


# ---------- LOCAL FAKE API SERVER ----------

class FakeApi:
    """Answers GET /rates with whatever `behavior` says. Records the requests."""

    def __init__(self):
        self.behavior = {"status": 200, "body": b"[]", "delay": 0.0, "headers": {}}
        self.queue = []                      # answers used first, one per request
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):               # noqa: N802 (name required by http.server)
                owner.requests.append(self.path)
                answer = owner.queue.pop(0) if owner.queue else owner.behavior
                if answer["delay"]:
                    threading.Event().wait(answer["delay"])
                try:
                    self.send_response(answer["status"])
                    headers = {"Content-Type": "application/json", **answer["headers"]}
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.send_header("Content-Length", str(len(answer["body"])))
                    self.end_headers()
                    self.wfile.write(answer["body"])
                except (BrokenPipeError, ConnectionResetError):
                    pass                      # client gave up (timeout test)

            def log_message(self, *args):     # keep the console clean
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v2"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def make(payload=None, status=200, body=None, delay=0.0, headers=None):
        return {"status": status, "delay": delay, "headers": headers or {},
                "body": body if body is not None else json.dumps(payload).encode()}

    def answer(self, *args, **kwargs):
        self.queue = []
        self.behavior = self.make(*args, **kwargs)

    def then(self, *args, **kwargs):
        """Queue an answer to be used before the standing one (first request first)."""
        self.queue.append(self.make(*args, **kwargs))

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


# ---------- HELPERS ----------

def hashes(folder):
    result = {}
    if folder.exists():
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                result[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def fresh_case(name, files=(FILE_1, FILE_2)):
    base = SANDBOX / name
    shutil.rmtree(base, ignore_errors=True)
    (base / "input").mkdir(parents=True)
    for file_name in files:
        shutil.copy(RAW / FILE_1 if file_name == "enrollments_2026-10-24.csv" else RAW / file_name,
                    base / "input" / file_name)
    return base


def run(case, mode, fake_url, timeout=5.0, rates_file=None, external=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = run_workflow.main(case / "input", case / "output", external or case / "external",
                                 mode, rates_file, fake_url, timeout)
    return code, out.getvalue().strip()


def last_history(case):
    path = case / "output" / "run_history.csv"
    return pd.read_csv(path, keep_default_na=False).iloc[-1] if path.exists() else None


def completed_folder(case):
    folders = sorted((case / "output" / "completed").glob("*"))
    return folders[-1] if folders else None


def external_files(case, external=None):
    folder = external or case / "external"
    return sorted(p.name for p in folder.glob("*")) if folder.exists() else []


RESULTS = []


def record(test_id, title, setup, expected, actual, passed):
    RESULTS.append((test_id, title, setup, expected, actual, bool(passed)))
    print(f"{'PASS' if passed else 'FAIL'}  {test_id}  {title}")


def failed_run_check(test_id, title, setup, expected_words, case, code, text):
    """Common checks for a run that must fail cleanly."""
    last = last_history(case)
    log = next((case / "output" / "failed").glob("*/run.log"), None)
    no_outputs = completed_folder(case) is None
    no_saved = external_files(case) == []
    words_ok = all(w.lower() in last["message"].lower() for w in expected_words) if last is not None else False
    passed = (code == 1 and last is not None and last["status"] == "FAILED" and words_ok
              and log is not None and no_outputs and no_saved)
    actual = (f"exit code {code}; history status {last['status'] if last is not None else '-'}; "
              f"message: {last['message'] if last is not None else '-'}; "
              f"nothing in completed/: {no_outputs}; nothing saved in external/: {no_saved}")
    record(test_id, title, setup,
           f"exit code 1, run filed under failed/ with a log, message mentions {expected_words}, "
           "no result files and no response saved", actual, passed)


# ---------- TESTS ----------

def test_live_and_saved(fake):
    case = fresh_case("S1_S2_live_then_saved")
    st4_before = hashes(PROJECT / "output")
    raw_before = hashes(RAW)
    fake.answer(GOOD_RATES)
    code, text = run(case, "live", fake.url)
    folder = completed_folder(case)
    saved = external_files(case)
    request = fake.requests[-1]
    wanted = ["from=2026-10-14", "to=2026-10-22", "base=USD", "quotes=BRL", "providers=BCB"]
    params_ok = all(w in request for w in wanted)
    rows = pd.read_csv(folder / "integrated_enrollments.csv") if folder else None
    brl = Decimal(str(round(rows["semester_total_brl"].sum(), 2))) if rows is not None else None
    last = last_history(case)
    record("S1", "Live mode with a normal answer",
           "Local fake API returns 7 synthetic rates (10-14 to 10-22); 10 enrollments in 2 files",
           f"Completed; GET parameters {wanted}; response + metadata saved; integrated CSV with 10 rows "
           f"and BRL total {EXPECTED_BRL}; history says live",
           f"exit {code}; request {request}; saved {saved}; rows {len(rows) if rows is not None else '-'}; "
           f"BRL total {brl}; history mode {last['source_mode'] if last is not None else '-'}",
           code == 0 and params_ok and len(saved) == 2 and rows is not None and len(rows) == 10
           and brl == EXPECTED_BRL and last["source_mode"] == "live")

    # saved mode on the file saved above (no server involved: nothing should be requested)
    before = len(fake.requests)
    code2, _ = run(case, "saved", fake.url)
    folder2 = sorted((case / "output" / "completed").glob("*"))[-1]
    rows2 = pd.read_csv(folder2 / "integrated_enrollments.csv")
    last2 = last_history(case)
    report = (folder2 / "enrollment_report.txt").read_text(encoding="utf-8")
    record("S2", "Saved mode reuses the saved response",
           "Same folder as S1, run again with --mode saved",
           "Completed without any request to the API; same BRL total; a second run folder; "
           "history says saved; report states SAVED mode",
           f"exit {code2}; new requests {len(fake.requests) - before}; "
           f"BRL {round(rows2['semester_total_brl'].sum(), 2)}; run folders "
           f"{len(list((case / 'output' / 'completed').glob('*')))}; mode {last2['source_mode']}",
           code2 == 0 and len(fake.requests) == before
           and Decimal(str(round(rows2["semester_total_brl"].sum(), 2))) == EXPECTED_BRL
           and len(list((case / "output" / "completed").glob("*"))) == 2
           and last2["source_mode"] == "saved" and "SOURCE MODE: SAVED" in report)

    # workbook content
    book = pd.read_excel(folder / "enrollment_workbook_st5.xlsx", sheet_name=None)
    info = dict(zip(book["Run_Info"]["item"], book["Run_Info"]["value"]))
    ok = (list(book) == run_workflow.WORKBOOK_SHEETS and len(book["Enrollments"]) == 10
          and "Provider" in info and info["Source mode"] == "live" and "Use conditions" in info
          and "127.0.0.1" in info["Endpoint"])
    record("S3", "Workbook and report document the external information",
           "Open the workbook and report written by S1",
           "Four sheets; 10 enrollment rows; Run_Info lists provider, endpoint, parameters, acquisition "
           "time, units, use conditions, source mode (endpoint is the local test server)",
           f"sheets {list(book)}; run info items {list(info)}; mode {info.get('Source mode')}", ok)

    # ST4 and raw data untouched
    same = hashes(PROJECT / "output") == st4_before and hashes(RAW) == raw_before
    record("S4", "ST4 outputs and raw data are preserved",
           "SHA-256 of every file in output/ (ST4 results) and data/raw/st4 before and after S1-S3",
           "Identical", "Identical" if same else "DIFFERENT", same)
    return case


def test_saved_problems(fake, good_case):
    case = fresh_case("S5_saved_without_file")
    code, _ = run(case, "saved", fake.url)
    failed_run_check("S5", "Saved mode with nothing saved", "Empty external/ folder, --mode saved",
                     ["No saved response"], case, code, "")

    case = fresh_case("S6_tampered_file")
    ext = case / "external"
    shutil.copytree(good_case / "external", ext)
    target = next(p for p in ext.glob("frankfurter_*.json") if not p.name.endswith("metadata.json"))
    original = target.read_bytes()
    target.write_bytes(original.replace(b'"rate": 5.2}', b'"rate": 9.9}'))
    assert target.read_bytes() != original, "test setup did not change the file"
    before = external_files(case)
    code, _ = run(case, "saved", fake.url)
    last = last_history(case)
    record("S6", "Saved response changed after saving",
           "Copy of the S1 saved response with one rate edited by hand (checksum no longer matches)",
           "Failed with a checksum message; no result files",
           f"exit {code}; message: {last['message']}",
           code == 1 and "checksum" in last["message"] and completed_folder(case) is None
           and external_files(case) == before)


def test_api_problems(fake):
    case = fresh_case("S7_timeout")
    fake.answer(GOOD_RATES, delay=3.0)
    code, text = run(case, "live", fake.url, timeout=0.5)
    failed_run_check("S7", "API does not answer in time", "Fake API waits 3 s; timeout set to 0.5 s",
                     ["did not answer within", "gave up after 3 attempts"], case, code, text)

    case = fresh_case("S8_http_500")
    fake.answer(status=500, body=b"boom")
    code, text = run(case, "live", fake.url)
    failed_run_check("S8", "HTTP 500", "Fake API answers 500", ["HTTP 500"], case, code, text)

    case = fresh_case("S9_http_503")
    fake.answer(status=503, body=b"busy", headers={"Retry-After": "30"})
    requests_before = len(fake.requests)
    code, text = run(case, "live", fake.url)
    failed_run_check("S9", "HTTP 503 with a long Retry-After",
                     "Fake API answers 503 + Retry-After: 30 (program accepts at most 10 s)",
                     ["HTTP 503", "Retry-After=30", "try again later"], case, code, text)
    stopped_at_once = len(fake.requests) - requests_before == 1
    record("S9b", "A long Retry-After stops the run without retrying",
           "Same case as S9, counting the requests the fake API received",
           "Exactly 1 request", f"{len(fake.requests) - requests_before} request(s)", stopped_at_once)

    case = fresh_case("S10_http_422")
    fake.answer(status=422, body=b"{}")
    code, text = run(case, "live", fake.url)
    failed_run_check("S10", "HTTP 422", "Fake API answers 422", ["HTTP 422"], case, code, text)

    case = fresh_case("S11_connection_refused")
    dead = FakeApi()
    dead_url = dead.url
    dead.stop()
    code, text = run(case, "live", dead_url)
    failed_run_check("S11", "Connection refused", "No server listening at the address",
                     ["Could not connect"], case, code, text)


def test_unsuitable_data(fake):
    variants = [
        ("S12", "Not JSON", dict(body=b"<html>maintenance</html>"), ["not valid JSON"]),
        ("S13", "JSON with another structure", dict(payload={"rates": {"2026-10-21": {"BRL": 5.2}}}),
         ["expected a list"]),
        ("S14", "Empty list", dict(payload=[]), ["no rates"]),
        ("S15", "Rate is text", dict(payload=[rate_item("2026-10-21", "5.20")]), ["not a number"]),
        ("S16", "Rate is zero", dict(payload=[rate_item("2026-10-21", 0)]), ["positive"]),
        ("S17", "Rate is negative", dict(payload=[rate_item("2026-10-21", -5.2)]), ["positive"]),
        ("S18", "Missing field", dict(payload=[{"date": "2026-10-21", "rate": 5.2}]), ["lacks field"]),
        ("S19", "Date is not a date", dict(payload=[rate_item("21/10/2026", 5.2)]), ["YYYY-MM-DD"]),
        ("S20", "Wrong quote currency (EUR instead of BRL)",
         dict(payload=[rate_item("2026-10-21", 0.92, quote="EUR")]), ["Unexpected currencies"]),
        ("S21", "Two rates for the same date",
         dict(payload=GOOD_RATES + [rate_item("2026-10-21", 5.3)]), ["same date"]),
        ("S22", "Implausible rate (unit change, e.g. 520.0)",
         dict(payload=[rate_item("2026-10-21", 520.0), rate_item("2026-10-22", 525.0)]), ["Implausible"]),
    ]
    for test_id, title, answer, words in variants:
        case = fresh_case(f"{test_id}_{title.split()[0].lower()}")
        fake.answer(**answer)
        code, text = run(case, "live", fake.url)
        failed_run_check(test_id, title, "Fake API answers HTTP 200 with data that is not suitable",
                         words, case, code, text)

    # valid data that does not cover the enrollment dates
    case = fresh_case("S23_no_coverage")
    fake.answer([rate_item("2026-10-01", 5.0), rate_item("2026-10-02", 5.0)])
    code, text = run(case, "live", fake.url)
    last = last_history(case)
    failed = next((case / "output" / "failed").glob("*"), None)
    unmatched = pd.read_csv(failed / "unmatched_enrollments.csv") if failed and (failed / "unmatched_enrollments.csv").exists() else None
    record("S23", "Valid rates that do not cover the enrollment dates",
           "Fake API returns only rates from 2026-10-01/02; enrollments are 10-21 and 10-22",
           "Failed (no rate within 5 days); incomplete result kept apart: unmatched_enrollments.csv in "
           "failed/ with 10 rows; nothing in completed/",
           f"exit {code}; message: {last['message']}; unmatched rows "
           f"{len(unmatched) if unmatched is not None else '-'}; completed/ empty {completed_folder(case) is None}",
           code == 1 and "no exchange rate" in last["message"] and unmatched is not None
           and len(unmatched) == 10 and completed_folder(case) is None)


def test_weekend_and_names(fake):
    case = fresh_case("S24_weekend", files=("enrollments_2026-10-24.csv",))   # a Saturday
    fake.answer(GOOD_RATES + [rate_item("2026-10-23", 5.3000)])
    code, _ = run(case, "live", fake.url)
    folder = completed_folder(case)
    rows = pd.read_csv(folder / "integrated_enrollments.csv") if folder else None
    ok = (code == 0 and rows is not None and set(rows["fx_rate_date"]) == {"2026-10-23"}
          and set(rows["rate_match"]) == {"previous_publication_day"}
          and set(rows["enrollment_date"]) == {"2026-10-24"})
    record("S24", "Enrollment on a Saturday uses Friday's rate and says so",
           "File enrollments_2026-10-24.csv (Saturday); the fake API has a rate for Friday 10-23 only",
           "Completed; rate_date 2026-10-23; rate_match previous_publication_day; report says 5 of 5 used "
           "the previous rate",
           f"exit {code}; rate dates {set(rows['fx_rate_date']) if rows is not None else '-'}; "
           f"match {set(rows['rate_match']) if rows is not None else '-'}",
           ok and "5 of 5 enrollments used the previous published rate"
           in (folder / "enrollment_report.txt").read_text(encoding="utf-8"))

    case = fresh_case("S25_bad_file_name")
    shutil.copy(RAW / FILE_1, case / "input" / "enrollments_today.csv")
    (case / "input" / FILE_1).unlink()
    (case / "input" / FILE_2).unlink()
    fake.answer(GOOD_RATES)
    code, _ = run(case, "live", fake.url)
    failed_run_check("S25", "File name without a date", "Only enrollments_today.csv in the input folder",
                     ["Cannot read a date"], case, code, "")


def test_retries_fixture_and_snapshot(fake):
    # S30: temporary failure, then success
    case = fresh_case("S30_retry_then_success")
    fake.answer(GOOD_RATES)
    fake.then(status=503, body=b"busy", headers={"Retry-After": "0"})
    before = len(fake.requests)
    code, _ = run(case, "live", fake.url)
    log = (next((case / "output" / "completed").glob("*")) / "run.log").read_text(encoding="utf-8") if completed_folder(case) else ""
    record("S30", "Temporary 503 is retried and the run completes",
           "Fake API answers 503 (Retry-After 0) once, then the normal answer",
           "Completed after exactly 2 requests; the retry is in run.log",
           f"exit {code}; requests {len(fake.requests) - before}; retry logged {'Attempt 1 failed' in log}",
           code == 0 and len(fake.requests) - before == 2 and "Attempt 1 failed" in log)

    # S31: retries are bounded
    case = fresh_case("S31_retries_bounded")
    fake.answer(status=503, body=b"busy", headers={"Retry-After": "0"})
    before = len(fake.requests)
    code, text = run(case, "live", fake.url)
    failed_run_check("S31", "Retries are limited to 3 attempts", "Fake API always answers 503 (Retry-After 0)",
                     ["HTTP 503", "gave up after 3 attempts"], case, code, text)
    record("S31b", "Exactly 3 requests were sent", "Same case as S31", "3 requests",
           f"{len(fake.requests) - before} request(s)", len(fake.requests) - before == 3)

    # S32: HTTP 500 is not temporary -> no retry
    case = fresh_case("S32_no_retry_on_500")
    fake.answer(status=500, body=b"boom")
    before = len(fake.requests)
    code, text = run(case, "live", fake.url)
    failed_run_check("S32", "HTTP 500 is not retried", "Fake API answers 500", ["HTTP 500"], case, code, text)
    record("S32b", "Exactly 1 request was sent", "Same case as S32", "1 request",
           f"{len(fake.requests) - before} request(s)", len(fake.requests) - before == 1)

    # S33: HTML instead of JSON
    case = fresh_case("S33_html_content_type")
    fake.answer(status=200, body=b"<html>maintenance</html>", headers={"Content-Type": "text/html"})
    code, text = run(case, "live", fake.url)
    failed_run_check("S33", "Content-Type is HTML, not JSON", "Fake API answers 200 with Content-Type text/html",
                     ["Expected JSON"], case, code, text)

    # S34: fixture mode works with no network, is labeled, and does not touch external/
    case = fresh_case("S34_fixture_mode")
    dead = FakeApi()
    dead_url = dead.url
    dead.stop()
    code, _ = run(case, "fixture", dead_url)
    folder = completed_folder(case)
    rows = pd.read_csv(folder / "integrated_enrollments.csv") if folder else None
    report = (folder / "enrollment_report.txt").read_text(encoding="utf-8") if folder else ""
    brl = Decimal(str(round(rows["semester_total_brl"].sum(), 2))) if rows is not None else None
    last = last_history(case)
    record("S34", "Fixture mode runs without internet and is labeled synthetic",
           "--mode fixture with the project's synthetic fixture; the API address points to a closed port",
           f"Completed; BRL total {EXPECTED_BRL}; report says SOURCE MODE: FIXTURE and SYNTHETIC; "
           "history says fixture; nothing saved in external/",
           f"exit {code}; BRL {brl}; synthetic label {'SYNTHETIC DEMONSTRATION' in report}; "
           f"mode {last['source_mode'] if last is not None else '-'}; external {external_files(case)}",
           code == 0 and brl == EXPECTED_BRL and "SOURCE MODE: FIXTURE" in report
           and "SYNTHETIC DEMONSTRATION" in report and last["source_mode"] == "fixture"
           and external_files(case) == [])

    # S35: repeated valid run -> same business results, new folder
    code2, _ = run(case, "fixture", dead_url)
    folders = sorted((case / "output" / "completed").glob("*"))
    first = pd.read_csv(folders[0] / "integrated_enrollments.csv")
    second = pd.read_csv(folders[-1] / "integrated_enrollments.csv")
    record("S35", "Repeated valid run: same results, new run folder",
           "Run S34 a second time",
           "Two different run folders; integrated CSV files identical",
           f"exit {code2}; folders {len(folders)}; identical CSV {first.equals(second)}",
           code2 == 0 and len(folders) == 2 and first.equals(second))

    # S36: source snapshot and run info
    snap = folders[0] / "source_snapshot"
    names = sorted(p.name for p in snap.glob("*")) if snap.exists() else []
    same_input = (snap / FILE_1).exists() and (snap / FILE_1).read_bytes() == (RAW / FILE_1).read_bytes()
    book = pd.read_excel(folders[0] / "enrollment_workbook_st5.xlsx", sheet_name="Run_Info")
    info = dict(zip(book["item"], book["value"]))
    record("S36", "The run keeps a snapshot of its inputs and records the environment",
           "Look inside the run folder of S34 and its workbook Run_Info",
           "source_snapshot/ holds both enrollment files, the rates file and its metadata (identical copies); "
           "Run_Info has source mode meaning, business period 2026-10-21 to 2026-10-22, environment versions",
           f"snapshot files {names}; input identical {same_input}; business period {info.get('Business period')}; "
           f"environment {info.get('Environment')}",
           len(names) == 4 and same_input and info.get("Business period") == "2026-10-21 to 2026-10-22"
           and "pandas" in str(info.get("Environment")) and "SYNTHETIC" in str(info.get("Source mode meaning")))

    # S37: a missing fixture is a failure, never a silent switch to another mode
    case = fresh_case("S37_missing_fixture")
    empty = case / "no_fixture_here"
    out = io.StringIO()
    before = len(fake.requests)
    with contextlib.redirect_stdout(out):
        code = run_workflow.main(case / "input", case / "output", case / "external", "fixture", None,
                                 fake.url, 5.0, empty)
    last = last_history(case)
    record("S37", "Missing fixture fails visibly (no automatic change of mode)",
           "Fixture folder is empty; the fake API would have answered, but must not be used",
           "Failed with 'synthetic fixture is missing'; 0 requests to the fake API; nothing saved in external/",
           f"exit {code}; message: {last['message']}; requests to the API: {len(fake.requests) - before}",
           code == 1 and "fixture is missing" in last["message"] and external_files(case) == []
           and len(fake.requests) == before)


def test_join_rules():
    enrollments = pd.DataFrame({
        "enrollment_id": ["A", "B", "C"], "semester_total": [100.0, 200.0, 300.0],
        "enrollment_date": pd.to_datetime(["2026-10-21", "2026-10-21", "2026-10-22"]).astype("datetime64[ns]")})
    rates = pd.DataFrame({"rate_date": pd.to_datetime(["2026-10-21", "2026-10-22"]).astype("datetime64[ns]"),
                          "rate": [5.0, 6.0]})
    joined = integration.attach_rates(enrollments, rates)
    ok = (len(joined) == 3 and list(joined["enrollment_id"]) == ["A", "B", "C"]
          and list(joined["fx_rate"]) == [5.0, 5.0, 6.0] and joined["semester_total"].sum() == 600.0)
    record("S26", "Join keeps rows, order and totals (many enrollments -> one rate)",
           "3 enrollments (two on 10-21, one on 10-22) and 2 rates",
           "3 rows, same order, rates 5,5,6, USD total 600", f"rows {len(joined)}; rates {list(joined['fx_rate'])}", ok)

    duplicated = pd.concat([rates, rates.iloc[[0]]], ignore_index=True)
    try:
        integration.attach_rates(enrollments, duplicated)
        raised = False
    except integration.IntegrationError as error:
        raised = "repeated dates" in str(error)
    record("S27", "Duplicate date in the rate table is refused",
           "Rate table with 10-21 twice (would turn 2 rows into 4)", "IntegrationError 'repeated dates'",
           "raised" if raised else "not raised", raised)

    older = rates.copy()
    older["rate_date"] = older["rate_date"] - pd.Timedelta(days=30)
    joined = integration.attach_rates(enrollments, older)
    try:
        integration.check_integration(enrollments, joined)
        raised = False
    except integration.IntegrationError as error:
        raised = error.unmatched is not None and len(error.unmatched) == 3
    record("S28", "Rate too old is not used", "Rates 30 days before the enrollments, limit 5 days",
           "Rows are kept, rate empty, IntegrationError lists 3 unmatched enrollments",
           "as expected" if raised else "different", raised)

    broken = joined.copy().iloc[:2]
    try:
        integration.check_integration(enrollments, broken)
        raised = False
    except integration.IntegrationError as error:
        raised = "Row count changed" in str(error)
    record("S29", "A lost row is detected", "Join result with one row removed",
           "IntegrationError 'Row count changed'", "raised" if raised else "not raised", raised)


# ---------- RECORD ----------

def write_record():
    passed = sum(1 for r in RESULTS if r[5])
    lines = ["# ST5 Test Record", "",
             "Global Languages Academy - exchange-rate integration. Authors: Bryan Strey and Victor Luis Soares Brito.", "",
             f"Run on {datetime.now():%Y-%m-%d %H:%M} with Python {platform.python_version()}, "
             f"pandas {pd.__version__}, requests {api.requests.__version__}.", "",
             "> **What these tests prove.** The real API was not called. A local test server on this computer "
             "returned synthetic rates (invented for the tests, not market values). The tests show that the "
             "code handles normal and abnormal answers correctly. They do not show what the real Frankfurter "
             "API returns; that needs one real run (`python run_workflow.py --mode live`).", "",
             f"**Result: {passed} of {len(RESULTS)} tests passed.**", "",
             f"Expected BRL total for the normal case (hand calculation): {EXPECTED_BRL}.", "",
             "| ID | Test | Result |", "|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {'PASS' if r[5] else 'FAIL'} |" for r in RESULTS]
    lines.append("")
    for r in RESULTS:
        lines += [f"### {r[0]} - {r[1]} ({'PASS' if r[5] else 'FAIL'})", "",
                  f"- **Setup:** {r[2]}", f"- **Expected:** {r[3]}", f"- **Actual:** {r[4]}", ""]
    RECORD.write_text("\n".join(lines), encoding="utf-8")


def main():
    shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.mkdir(parents=True)
    fake = FakeApi()
    try:
        good_case = test_live_and_saved(fake)
        test_saved_problems(fake, good_case)
        test_api_problems(fake)
        test_unsuitable_data(fake)
        test_weekend_and_names(fake)
        test_retries_fixture_and_snapshot(fake)
        test_join_rules()
    finally:
        fake.stop()
    write_record()
    failures = [r[0] for r in RESULTS if not r[5]]
    print(f"\n{len(RESULTS) - len(failures)} of {len(RESULTS)} tests passed.")
    if failures:
        print("FAILED:", ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
