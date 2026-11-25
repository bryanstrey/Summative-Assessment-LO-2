# ST4 AI Interaction Documentation
## Global Languages Academy - Batch Enrollment Report

**Students:** Bryan Strey, Victor Luis Soares Brito

**AI tool and version:** Claude Sonnet 5.5 (Anthropic), used in the claude.ai chat, 23 October 2026

This document records, for the ST4 work: the prompt used, the relevant AI response and the
suggestions considered, the changes accepted or rejected and why, the test or data check used
to verify each adopted change, the observed result, and any remaining limitation. The ST1 and
ST2 interactions are in the earlier AI documentation.

*Note on the prompts:* the prompts are written out in full, including context established
earlier in the conversation. The original chat messages were shorter.

---

## 1. Building the ST4 workflow

**Prompt:** *"We now have the continuation of the project. I am sending the ST4 course project
document and the three study-topic decks (files and batch processing, spreadsheet automation,
reports and robustness). Continue the Global Languages Academy project from ST1 and ST2 and
build what ST4 asks: a batch of related CSV files, validation, an Excel workbook, a text report,
logs, tests, and documentation."*

**AI response:** The AI read the four PDFs, listed the ST4 deliverables (two or more CSVs,
reusable functions in `.py` files, processed CSVs, a workbook with two or more sheets, a report
with three or more indicators, at least three validation rules, logging, the five required
tests, README, AI record and declaration) and proposed adapting the ST2 language-school rules
to a batch of daily enrollment exports. It wrote `school_rules.py`, `validation.py`,
`run_report.py`, the sample data and `tests/run_tests.py`.

### Suggestions considered

| # | Suggestion | Decision and reason | Verification | Observed result |
|---|---|---|---|---|
| S1 | Use two simulated daily enrollment exports (5 rows each) as the batch | **Accepted.** The ST1-ST2 project has no CSV data, ST4 needs two related files, and the course examples are also simulated | Data dictionary in the README; independent calculation in test T1 | Valid batch passes. *Limitation:* the data are simulated |
| S2 | Reuse the five ST2 functions unchanged in `school_rules.py` | **Accepted.** The slides ask to reuse earlier logic. *Not adopted:* rewriting the rules as pandas column formulas, which would duplicate them | T1: all 10 row totals equal the manual calculation. A change of the coupon discount from 5% to 7% in a temporary copy made T1 fail | 10 of 10 totals match; the change was detected |
| S3 | Round money to cents in the batch step | **Accepted as a precaution.** With the school's three current prices every discount combination already lands on whole cents (checked by running all combinations). It matters if a price with cents is added, for example 400.07 with 5% gives 380.0665, rounded to 380.07 | Combination check described here; T1 values | No change in the current results. *Limitation:* the school's approved rounding rule is not defined |
| S4 | Validate every file before writing any output; one rejected file stops the whole batch | **Accepted** (required by the ST4 slides) | T2, T3, A1, A2, A3, A5, A9: the failed folder contains only `run.log` | All pass |
| S5 | Keep runs in `output/completed`, `output/failed` and `output/in_progress` | **Accepted** instead of the slides' single run folder, so that incomplete files are separated from completed results by folder, not only by the log | T2, T5, A6 | Failed runs never appear under `completed`; earlier runs stay byte-identical. *Limitation:* an interrupted run leaves a folder in `in_progress` |
| S6 | An unrecognized coupon code is a WARNING, not a rejection | **Accepted.** *Not adopted:* rejecting the batch, because the ST2 rule says other codes give no discount and the review prompt says not to change business rules | T1 checks the WARNING for `PROMO10` and the report note | Logged and reported. *Limitation:* a typing error in a valid code loses the discount without stopping the run |
| S7 | Write the workbook with numeric values, not Excel formulas | **Accepted.** The ST4.2 slides ask for numeric values and for verifying the workbook against the data; formulas written by openpyxl have no stored values until recalculated, which would break the read-back check | `verify_outputs()` and T1 read the workbook back | Row counts and totals reconcile. *Limitation:* editing a cell in Excel does not update other cells |
| S8 | Add a third sheet, `Run_Info` (run id, files, currency, rounding) | **Accepted** for traceability; the slides require at least two sheets | T1 checks the three sheet names | Pass |
| S9 | Add `--input-dir` and `--output-dir` options | **Accepted.** They allow the failed-run demonstration and the tests without touching the real outputs. The default command is still `python run_report.py` | Demonstration in `docs/demo_runs_console.txt`; all tests | Pass |
| S10 | Append one line per run to `output/run_history.csv` | **Accepted** so that users identify the latest run and its status | Checked in T2-T5, A1-A6, A8-A10 and the demonstration | The last line was the latest run in every case |

The expected values for test T1 (each enrollment's tuition and semester total, the revenue of
25845.00 and the discounts of 2205.00) were calculated from the business rules without using
the program's functions, and typed into the test script as constants.

---

## 2. AI-assisted workflow review

**Prompt (the ST4 review prompt, adapted):** *"Review my Python automation using the business
rules and file structure I provide. Check batch processing, consistent outputs, error handling,
and execution logs. Explain what happens if the second input file is invalid or an output write
fails. Suggest focused improvements and tests with expected results. Do not invent data or
change business rules."*

**AI response (summary):**

- *Second input file invalid:* the first file is read and validated, the second is rejected, and
  the whole batch stops before anything is written. The run is filed under `output/failed` with
  only its log (test T2).
- *Output write fails:* the run is marked FAILED, partial CSVs stay under `output/failed`, no
  final workbook or report exists, and earlier completed runs are untouched (test A6).
- Findings and proposed improvements:

| # | Finding or suggestion | Decision and reason | Verification | Observed result |
|---|---|---|---|---|
| F1 | Blank lines in a CSV shift the line numbers in error messages and in `source_line`, because pandas skips them. The defect was reproduced: an invalid row on file line 5 was reported as line 4 | **Accepted.** Wrong line numbers send the person correcting the file to the wrong place and weaken traceability. Fix: read blank lines as rows, drop the empty ones, keep the original index | New tests A7 (valid file with a blank line) and A8 (invalid row after a blank line). With the fix reverted in a temporary copy, A7 and A8 failed | Error now says line 5; `source_line` is 2, 4, 5, 6, 7. *Limitation:* line numbers still assume no field contains a line break |
| F2 | A semicolon-separated CSV (the default of Excel in some regions) gives a confusing "missing columns" error | **Accepted.** Added a specific message asking for a comma-separated UTF-8 file | New test A9 | Pass. Other separators and encodings remain unsupported |
| F3 | The "unexpected error" branch (a program defect) was never exercised | **Accepted.** Added a test that forces a `RuntimeError` | New test A10: the error is re-raised, logged with traceback, and the run is filed as failed | Pass |
| F4 | While injecting defects, the test runner stopped with an error instead of recording a FAIL when the program raised an unexpected error | **Accepted.** The runner now records an unexpected exception as a failed test | Repeated the injected defect (course validation removed): T2 is recorded as FAIL | Pass |
| F5 | Absolute paths of the computer appeared in the console, log, report and history | **Accepted.** Paths are shown relative to the project folder, so the evidence does not depend on one computer | Re-ran the demonstration; the output shows `output/failed/...` | Pass |
| F6 | The tests could pass without being able to fail | **Accepted.** Defects were injected into temporary copies of the project: coupon 5% changed to 7%, course validation removed, duplicate-key check removed, failed runs filed as completed, blank-line fix reverted | Each defect made at least one test fail; the copies are not part of the project | All five defects were detected |
| F7 | Compatibility with the pandas versions on students' computers | **Accepted.** Ran the whole test suite in a clean environment with pandas 2.2.3, and in the main one with pandas 3.0.2 | `python tests/run_tests.py` | 15 of 15 pass in both |

**Suggestions not adopted** (remaining limitations): reporting every error of a file at once
(only the first rule violated is reported); a lock to prevent two simultaneous runs; automatic
cleanup of `output/in_progress`; Excel formulas instead of values; support for other encodings.
They go beyond the ST4 requirements or need a business decision (for example, the approved
rounding rule).

**Final test result:** 15 of 15 tests passed (the 5 required and 10 additional); see
`docs/st4_test_record.md`.

---

## 3. Documentation and declaration

**Prompt:** *"Write the README, the project documentation (input agreement, reuse of earlier
work, business interpretation, limitations, demonstration of one failed and one successful
run), this AI record and the AI-use declaration required by the course plan."*

**AI response:** Drafted `README.md`, `docs/st4_project_documentation.md` and this document.

**Accepted:** The documents, after checking them against the project:

- every number in the reconciliation table was read from the generated CSVs, workbook and
  report, not typed;
- claims that could not be verified were removed or limited: the README states the Python
  version that was actually tested, and the rounding paragraph (S3) says that rounding does not
  change the current results.

**Not adopted:** Reuse of ST3 logic. The ST3 submission was not part of the material the AI
received, so the documents state that no ST3 code was used (project documentation, section 3.2).

**Remaining limitations:** The business interpretation in the report and in the documentation is
based on ten simulated enrollments and should not be read as a trend. The ST3 reuse requested by
the ST4 slides is not demonstrated.

---

## 4. Team understanding

Every team member must be able to explain the submitted solution. A step-by-step walkthrough of
one run and answers to the questions we should be able to answer are in
`docs/st4_project_documentation.md`, section 8.

---

## 5. AI-use declaration

During the preparation of this project (Python code, simulated input data, tests and
documentation), the authors used Claude Sonnet 5.5 (Anthropic) for designing the batch workflow,
writing and testing the Python code, creating the simulated sample data and the test cases,
reviewing the workflow for errors, and drafting the documentation. After using this tool, the
authors reviewed and edited the content as necessary and assume full responsibility for the
content.
