# ST4 Project Documentation
## Global Languages Academy - Batch Enrollment Report

**Course project:** AI-Assisted Python for Business Problem Solving (Prof. Evandro Zatti)

**Students:** Bryan Strey, Victor Luis Soares Brito

---

## 1. The recurring task

| Element | Global Languages Academy |
|---|---|
| Recurring task | Turn the daily enrollment exports into a checked revenue and discount report |
| Intended user | The school manager or front-desk supervisor |
| Input | One CSV per day (`enrollments_YYYY-MM-DD.csv`): who enrolled, in which course, with which discount facts |
| Processing | Validate every file, apply the school's pricing and discount rules, classify the discount level, summarize by course |
| Output | Processed CSVs, an Excel workbook, a text report with indicators, a log |
| Control | Originals are never changed; a rejected file stops the whole batch; every run has its own folder; failed runs are kept apart from completed ones |

## 2. Input agreement

| Requirement | Agreement for this project |
|---|---|
| Batch scope | Two related CSVs (`enrollments_2026-10-21.csv`, `enrollments_2026-10-22.csv`) with identical columns. Selection rule: every file named `enrollments_*.csv` in `data/raw/st4/` |
| Data meaning | One row = one enrollment of one student in one course for one semester. Required columns: `enrollment_id`, `student_name`, `course`, `sibling_enrolled`, `payment_method`, `renewal`, `coupon_code`. Business key: `enrollment_id` (unique across the batch) |
| Data origin | Simulated data created by the team with AI assistance (fictional students). Preserved originals in `data/raw/st4/`, with SHA-256 checksums in the README. No manual preparation steps; only the cleaning done by the program (trim spaces, standardize capitalization) |
| Processing | Reproducible: the same inputs give the same outputs (test T5). Checks: four validation rules, read-back of CSVs and workbook, comparison with independently calculated values (test T1) |
| Traceability | Every processed row carries `source_file` and `source_line`; the report lists the source files; the workbook has a `Run_Info` sheet; the log records every file read |

## 3. Reuse of earlier work

### 3.1 ST2 project

The five calculation functions come from `language_school.py` (ST2) and were moved to
`school_rules.py` with the **same logic**:

| Function | Status in ST4 |
|---|---|
| `get_course_price` | Unchanged |
| `calculate_total_discount` | Unchanged (the coupon code is now the constant `RECOGNIZED_COUPON`) |
| `classify_discount` | Unchanged (the `if / elif / else` decision rule) |
| `calculate_final_tuition` | Unchanged |
| `calculate_semester_total` | Unchanged (6 months is now the constant `SEMESTER_MONTHS`) |

Adaptations, each marked "ST4" in the code: `calculate_enrollment_fee()` (the fee rule that ST2
wrote inline in the main program), `is_recognized_coupon()` (so the batch can warn about
unknown codes), and rounding of money to cents in the batch step (ST2 only formatted to two
decimals when printing).

### 3.2 ST3

The cleaning, validation and aggregation steps of this workflow follow the patterns shown in
the ST4 course material: trimming and standardizing text, rule-based validation, and
`groupby().agg()` with sorting. The ST3 submission of the team was **not** used as an input to
this ST4 workflow, so no ST3 code is reused here.

## 4. Reconciliation of the results

The CSVs, the workbook and the report come from the same validated data and were compared in
the successful run (`output/completed/20261023_143906_424559/`) with the manual calculation
(see `docs/st4_test_record.md`):

| Measure | Manual calculation | Processed CSVs | Workbook (`Enrollments`) | Workbook (`By_Course`) | Report |
|---|---|---|---|---|---|
| Rows / enrollments | 10 | 10 | 10 | 10 | 10 |
| Projected semester revenue (USD) | 25845.00 | 25845.00 | 25845.00 | 25845.00 | 25845.00 |
| Discounts granted (USD) | 2205.00 | 2205.00 | 2205.00 | 2205.00 | 2205.00 |

`By_Course` (sorted by revenue): English 4 enrollments, USD 10035.00; French 3, USD 8076.00;
Spanish 3, USD 7734.00.

## 5. Business interpretation

**Calculated evidence** (from the validated data):

- 10 enrollments; projected semester revenue USD 25845.00.
- Discounts granted: USD 2205.00, which is 8.2% of list tuition (USD 27000.00).
- 3 of 10 enrollments (30%) received a High discount (15% or 20%); 3 of 10 are renewals.
- English has the highest projected revenue (USD 10035.00, 38.8% of the total) and also the most
  enrollments (4 of 10).

**Interpretation** (our reading, not a calculated value):

- *Finding.* Because sibling, upfront and coupon discounts stack, three enrollments received 15%
  or 20%. The manager may want to confirm that stacking up to 20% is intended before the next
  enrollment period. The report measures the discounts; it does not say whether they were
  appropriate.
- English leads in revenue partly because it has the most enrollments, not only because of its
  price (it has a lower base price than French). With ten simulated records this is not a trend.

**Limitation.** The results cover only the two selected files and are projections under the
school's rules, not payments received. One coupon code (`PROMO10`, enrollment E-1010) was not
recognized and received no discount; whether that is a typing error or a different promotion
must be checked in the source.

## 6. Limitations

1. The data are simulated. The program cannot prove that every real enrollment reached the
   input folder.
2. Input must be comma-separated UTF-8 CSV. Semicolon-separated files are rejected with a clear
   message; other encodings are not supported.
3. Line numbers in error messages assume that no field contains a line break.
4. Rounding to cents uses Python's `round`. The school's approved rounding rule is not defined.
5. Prices, discounts and courses are fixed in `school_rules.py`. A new course or a new coupon
   needs a code change, and the same text appears in the README.
6. Workbook amounts are numbers calculated by the program, not Excel formulas; editing a cell
   in Excel does not update other cells.
7. Only the first invalid rule found in a file is reported, so a file with several problems may
   need more than one correction round.
8. Two runs started at the same moment are not coordinated, and an interrupted run leaves a
   folder in `output/in_progress/` that must be deleted by hand.
9. An unknown coupon code is a warning, not a rejection (the ST2 rule gives it no discount).
   A typing error in a valid code, such as `PROMO 5`, therefore loses the discount without
   stopping the run; it is visible in the log and the report.

## 7. Demonstration: one failed run and one successful run

The folder `data/demo_failure/` is a copy of the inputs where the course of enrollment E-1008
was changed from `Spanish` to `Italian`. Console output is in `docs/demo_runs_console.txt`.

### 7.1 Failed run

```
python run_report.py --input-dir data/demo_failure
Run 20261023_143904_356322 FAILED: enrollments_2026-10-22.csv: invalid course ['Italian'] on CSV line(s) [4]; allowed values: ['English', 'Spanish', 'French']
Details: output/failed/20261023_143904_356322/run.log
[exit code: 1]
```

**Evidence**

- The log (`output/failed/20261023_143904_356322/run.log`) shows the first file validated
  (5 rows), then `ERROR FAILED: enrollments_2026-10-22.csv: invalid course ['Italian'] on CSV
  line(s) [4]`.
- The folder `output/failed/20261023_143904_356322/` contains only `run.log`: the first file was
  valid, but the batch stopped, so no processed CSV, workbook or report exists.
- `output/run_history.csv` has a `FAILED` row with the same message.

**Correction needed.** Open `enrollments_2026-10-22.csv`, go to line 4 (E-1008) and replace
`Italian` with the right course (`Spanish`). Run the command again.

### 7.2 Successful run (after the correction, with the real data)

```
python run_report.py
Run 20261023_143906_424559 COMPLETED: 10 enrollments from 2 file(s).
Outputs: output/completed/20261023_143906_424559
[exit code: 0]
```

**Evidence**

- `output/completed/20261023_143906_424559/` holds the two processed CSVs, the workbook, the
  report and the log.
- The log shows every step: files selected, each file validated, the WARNING for coupon
  `PROMO10`, outputs written, `Verified CSVs and workbook: rows=10 total=25845.00`, `COMPLETED`.
- `output/run_history.csv` shows the two runs in order: the `FAILED` run, then the `COMPLETED`
  one. The last line is the latest run.

## 8. Explaining the solution

**One run, step by step** (`main()` in `run_report.py`):

1. Create the run id (the start time) and a work folder `output/in_progress/<run_id>/`; start
   the log.
2. `select_input_files()` finds `enrollments_*.csv`; stops if the folder or the files are missing.
3. `load_batch()` reads every file as text, validates it (`validation.py`), adds `source_file` and
   `source_line`, stacks the files, and checks that `enrollment_id` is unique.
4. `process_enrollments()` applies the ST2 functions in `school_rules.py` to each row.
5. `write_processed_csvs()`, `write_workbook()` (with `build_course_summary()`) write the outputs.
6. `verify_outputs()` reads the CSVs and the workbook back and compares rows and totals.
7. `make_report_text()` and `write_report()` write the report (draft first, then renamed).
8. The folder is moved to `output/completed/` or `output/failed/`, and a line is added to
   `output/run_history.csv`.

**Questions we should be able to answer**

- *Why validate every file before writing anything?* A rejected file must stop the whole batch,
  and a partial report could be mistaken for a complete one.
- *Why separate `completed`, `failed` and `in_progress`?* So that anyone can tell a finished
  result from an incomplete one by the folder alone.
- *Why `mode="x"` and `"xb"` when writing?* They refuse to overwrite an existing file, so an
  earlier result cannot be replaced by accident.
- *Why read every value as text?* To see exactly what the file contains. Pandas would otherwise
  turn some text (for example `NA`) into missing values.
- *Why is an unknown coupon a warning and not an error?* The ST2 business rule says such a code
  gives no discount; stopping the batch would change that rule.
- *How do we add a course?* Add it to `COURSE_PRICES` in `school_rules.py`; validation and
  processing use that dictionary.
- *What happens if the second file is invalid, or a write fails?* The first case is test T2 and
  the second is test A6 (`docs/st4_test_record.md`).

## 9. AI-use declaration

During the preparation of this project (Python code, simulated input data, tests and
documentation), the authors used Claude Sonnet 5.5 (Anthropic) for designing the batch workflow,
writing and testing the Python code, creating the simulated sample data and the test cases,
reviewing the workflow for errors, and drafting the documentation. After using this tool, the
authors reviewed and edited the content as necessary and assume full responsibility for the
content.

The record of the AI interaction is in `docs/st4_ai_interaction_documentation.md`.
