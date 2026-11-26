# Global Languages Academy - Batch Enrollment Report (ST4)

**Course project:** AI-Assisted Python for Business Problem Solving (Prof. Evandro Zatti)

**Students:** Bryan Strey and Victor Luis Soares Brito

## 1. Purpose

Global Languages Academy enrolls students every day. The front desk exports each day's
enrollments to a CSV file. At the end of an enrollment period, the manager needs the
**projected semester revenue**, the **discounts granted**, and a list of every enrollment
with its calculated tuition, without recalculating by hand.

This program repeats that task on every run: it takes all the daily export files, checks
them, applies the school's pricing and discount rules (the ST2 project), and produces:

- one processed CSV per input file,
- one Excel workbook (detailed records + summary by course + run information),
- one short text report with business indicators,
- a log of the run.

**Intended user:** the school manager or front-desk supervisor.

## 2. How to run

From the project folder:

```
python run_report.py
```

Exit code `0` means the run completed; `1` means it failed (the reason is printed and logged).

Optional, to run on other folders (used for the failure demonstration and the tests):

```
python run_report.py --input-dir data/demo_failure
```

To run the tests: `python tests/run_tests.py`

## 3. Dependencies

Python 3, `pandas` and `openpyxl`:

```
python -m pip install -r requirements.txt
```

Tested only with Python 3.12, pandas 3.0.2 and 2.2.3, and openpyxl 3.1.5.

## 4. Folder structure

| Path | Purpose |
|---|---|
| `run_report.py` | Main workflow (the run command) |
| `school_rules.py` | Business rules: the ST2 functions plus two small ST4 additions |
| `validation.py` | Cleaning and validation rules |
| `data/raw/st4/` | **Original** input CSVs. Only read, never changed |
| `data/demo_failure/` | Copy of the inputs with one invalid course, used for the failed-run demonstration |
| `output/completed/<run_id>/` | Complete results of each successful run |
| `output/failed/<run_id>/` | Log (and any partial files) of each failed run |
| `output/in_progress/<run_id>/` | Work area during a run; only remains if a run was interrupted |
| `output/run_history.csv` | One line per run with its status |
| `tests/run_tests.py` | The test runner; `tests/test_runs/` holds each test's evidence |
| `docs/` | Test record, project documentation, AI documentation, demonstration output |

## 5. Input selection

**Selection rule:** every file named `enrollments_*.csv` directly inside `data/raw/st4/`
(sorted by name). Other files are ignored. Output folders are separate, so a run never reads
its own results. If no file matches, the run fails.

**Meaning of one row:** one enrollment of one student in one course for one semester.

**Business key:** `enrollment_id`, unique across the whole batch.
Files must be comma-separated UTF-8 CSV.

| Column | Meaning | Allowed values |
|---|---|---|
| `enrollment_id` | Unique enrollment code | Any non-blank text, e.g. `E-1001` |
| `student_name` | Student | Non-blank text |
| `course` | Course enrolled | `English`, `Spanish`, `French` |
| `sibling_enrolled` | A sibling is also enrolled | `yes`, `no` |
| `payment_method` | How the semester is paid | `upfront`, `monthly` |
| `renewal` | Renewal of an existing enrollment | `yes`, `no` |
| `coupon_code` | Promotional code | Blank, or text; only `PROMO5` gives a discount |

Text is trimmed and capitalization is standardized before validation (for example `english`
is read as `English`).

**Data origin:** the two files are **simulated** data created by the team with AI assistance
for this project (fictional students). They represent two days of front-desk exports
(21 and 22 October 2026). No manual preparation was applied; the files are kept exactly as
created. SHA-256 of the originals:

- `enrollments_2026-10-21.csv`: `4ea4d63f63ae62a24cf42a830dbaebf34895b30c2861399921948520497c3cf9`
- `enrollments_2026-10-22.csv`: `9d3c87aa92c713278e43c2a76419fd35e51b02668afd040957fa554278c8a8e0`

## 6. Business rules (from the ST2 project)

| Rule | Value |
|---|---|
| Base monthly tuition | English 450.00, Spanish 420.00, French 480.00 (USD) |
| Sibling enrolled discount | 10% |
| Upfront payment discount | 5% |
| Coupon `PROMO5` discount | 5% |
| Discounts | Cumulative (maximum 20%) |
| Enrollment fee | USD 150.00 once per semester; 0.00 on renewal |
| Semester | 6 months |
| Discount level (decision rule) | 0% No discount; up to 5% Low; up to 10% Medium; above 10% High |

Money values are rounded to cents. A coupon code other than `PROMO5` gives no discount
(the ST2 rule); the run continues and a WARNING is logged.

## 7. Validation rules

A rejected file stops the **whole batch**: nothing is published.

| # | Rule | Why |
|---|---|---|
| 1 | Exact expected columns, in order, and at least one data row | A missing or renamed column would shift or lose information |
| 2 | `enrollment_id` and `student_name` not blank | Each record must be identifiable and traceable |
| 3 | `course`, `sibling_enrolled`, `payment_method`, `renewal` only allowed values | The pricing and discount rules exist only for those values; a typo would give a wrong total |
| 4 | `enrollment_id` unique across all files | A repeated enrollment would be counted twice in revenue |
| - | After processing, CSVs and workbook are read back and must show the same row count and total as the validated data | Detects a faulty write |

Error messages name the file, the CSV line numbers and the value, for example:
`enrollments_2026-10-22.csv: invalid course ['Italian'] on CSV line(s) [4]; allowed values: [...]`.

## 8. Output files

Each successful run creates `output/completed/<run_id>/` (the run id is the start time,
`YYYYMMDD_HHMMSS_microseconds`):

| File | Content |
|---|---|
| `processed/<source>_processed.csv` | The input rows plus base tuition, discount, level, final tuition, fee, semester total, list tuition, discount amount, `source_file`, `source_line` |
| `enrollment_workbook.xlsx` | Sheets `Enrollments` (detail with source file), `By_Course` (summary sorted by revenue) and `Run_Info` |
| `enrollment_report.txt` | Run id, source files, indicators, one finding and limitations |
| `run.log` | Timestamped events: start, files read, validation, warnings, outputs, result |

The workbook has styled headers, widths, USD number formats, frozen header row and filters.
Amounts are stored as numbers (not text). Values are calculated by the program, not Excel
formulas.

## 9. Indicators

| Indicator | Definition |
|---|---|
| Enrollments | Count of unique `enrollment_id` |
| Projected semester revenue (USD) | Sum of `semester_total` = final tuition x 6 + enrollment fee |
| Discounts granted (USD) | Sum of (base tuition - final tuition) x 6; the fee is not discounted |
| Discounts as % of list tuition | Discounts granted / sum of (base tuition x 6) |
| High-discount enrollments | Count and share with level "High discount" (more than 10%) |
| Renewals | Count with `renewal = yes` (fee waived) |
| Top course by projected revenue | First row of `By_Course` |

## 10. When a run fails

- Everything is validated **before** any output is written, so a data problem leaves no CSV,
  workbook or report.
- The run folder is moved to `output/failed/<run_id>/`. It contains `run.log` (and, if the
  failure happened while writing, only partial files) and **never** a final report or workbook.
- Earlier completed runs are never modified; each run has its own folder.
- The console prints `Run <id> FAILED: <reason>` and the path of the log.
- If the program has a defect (an unexpected error), the traceback is written to the log, the
  error is re-raised, and the run is filed as failed.

**Finding the latest run and its status:** open `output/run_history.csv`. The **last line** is
the latest run; the `status` column is `COMPLETED` or `FAILED`, and `run_folder` points to its
folder. A run is complete only if its folder is under `output/completed/`.

A folder left in `output/in_progress/` means the run was interrupted (for example, the
computer was switched off). It is never treated as complete and can be deleted.

## 11. Tests

`python tests/run_tests.py` runs the five required tests (valid batch, invalid business-rule
value, missing column, no matching files, second run) and ten additional tests, and writes
`docs/st4_test_record.md` with setup, expected result, actual result and pass/fail for each.
Expected values for the valid batch were calculated manually, without the program's functions.

## 12. Known limitations

- Input must be comma-separated UTF-8 CSV; other separators or encodings are rejected.
- Line numbers in error messages assume that no field contains a line break.
- Rounding to cents uses Python's `round`; the school's approved rounding rule is not defined.
- Menu values and prices are fixed in `school_rules.py`; a new course needs a code change.
- Two runs started at the same moment are not coordinated.
- The data are simulated; the program cannot prove that every real enrollment reached the folder.

More detail: `docs/st4_project_documentation.md`.

## 13. Documentation index

| File | Content |
|---|---|
| `docs/st4_project_documentation.md` | Input agreement, ST2/ST3 reuse, business interpretation, demonstration, explaining the solution |
| `docs/st4_test_record.md` | Test record (generated by the test runner) |
| `docs/st4_ai_interaction_documentation.md` | AI record and AI-use declaration |
| `docs/demo_runs_console.txt` | Console output of the demonstrated failed and successful runs |


---

# ST5 extension - exchange rates from an external API

**Question answered:** what is the projected semester revenue in BRL, using the USD->BRL rate of the day of each enrollment file?

**Status:** code and tests complete. The real API was called on 25 Nov 2026 (live run `20261125_203148_552931`, saved run `20261125_203151_244041`): USD 25 845.00 = **BRL 130 078.86**. `output/st5/completed/` also holds the **synthetic fixture** demonstration (invented rates, labeled FIXTURE); check the source mode of each run.

## How to run

```
python run_workflow.py                        # = --mode fixture: SYNTHETIC demonstration data, no internet
python run_workflow.py --mode live            # calls the API, validates, saves the answer in data/external/
python run_workflow.py --mode saved           # reuses the latest saved real answer (works offline)
python tests/run_tests_st5.py                 # 40 checks with a local fake API (synthetic rates)
```

Exit code 0 = completed, 1 = failed (reason printed and logged). Options: `--rates-file`, `--input-dir`, `--output-dir`, `--external-dir`, `--fixture-dir`, `--timeout`. A failed mode never falls back to another mode.

## New files

| Path | Purpose |
|---|---|
| `exchange_api.py` | GET request, save/load response + metadata, JSON inspection, DataFrame, validation |
| `integration.py` | Join key, uniqueness, `merge_asof`, BRL conversion, integrity checks |
| `run_workflow.py` | The ST5 run command (reuses the ST4 functions unchanged) |
| `data/external/` | Saved REAL API responses + metadata (one per live run) |
| `data/fixtures/` | SYNTHETIC rates + metadata for `--mode fixture` (created by `tests/make_fixture.py`) |
| `output/st5/completed/<run_id>/` | `integrated_enrollments.csv`, `enrollment_workbook_st5.xlsx`, `enrollment_report.txt`, `run.log`, `source_snapshot/` |
| `output/st5/failed/<run_id>/` | Log of failed runs (and `unmatched_enrollments.csv` if enrollments had no rate) |
| `tests/run_tests_st5.py`, `tests/test_runs_st5/` | ST5 tests and their evidence (synthetic data) |
| `docs/st5_api_and_integration.md` | Documentation for criteria 5.1-5.3 |
| `docs/st5_test_record.md` | Test record |
| `docs/st5_demo_runs_console.txt` | Console output of the demonstration runs |
| `docs/st5_ai_interaction_documentation.md` | Criterion 5.4 (with a section the team fills in after the live run) |

ST4 files (`run_report.py`, `school_rules.py`, `validation.py`) and ST4 results in `output/` are unchanged.
