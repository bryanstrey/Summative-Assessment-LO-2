# Summative Assessment - LO 2

**Course:** AI-Assisted Python for Business Problem Solving (Prof. Evandro Zatti)
**Students:** Bryan Strey, Victor Luis Soares Brito

Global Languages Academy is a (fictional) language school. This repository contains two stages
of the same project:

- **ST4 - Batch enrollment report.** Reads the school's daily enrollment CSV files, validates them,
  applies the pricing and discount rules (tuition in USD) and produces processed CSVs, an Excel
  workbook, a text report and a log.
- **ST5 - Exchange-rate integration.** Answers the question *"What is the projected semester revenue
  in BRL, using the USD→BRL rate of the day of each enrollment file?"* It calls the Frankfurter API
  (Banco Central do Brasil PTAX rates), saves and validates the response, joins the rates to the
  enrollments by date and produces an integrated CSV, a workbook, a report and a log.

**Real result (live run of 25 Nov 2026):** USD 25 845.00 = **BRL 130 078.86**
(21 Oct: 5.0277 BRL/USD; 22 Oct: 5.0383 BRL/USD).

## Repository contents

| Path | Content |
|---|---|
| `language_school_st4/` | The full project: code, data, outputs, tests and documentation (ST4 and ST5) |
| `st5_api_and_integration.pdf` | ST5 documentation: API, data integration and workflow (criteria 5.1-5.3) |
| `st5_test_record.pdf` | ST5 test record (40 of 40 tests passed) |
| `st5_ai_interaction_documentation.pdf` | AI interaction documentation and team verification (criterion 5.4) |
| `language_school_st5.zip` | The `language_school_st4/` folder packed as a single file for submission |

Inside `language_school_st4/`:

| Path | Purpose |
|---|---|
| `run_report.py` | ST4 run command (batch enrollment report) |
| `school_rules.py`, `validation.py` | Business rules (from ST2) and validation rules |
| `run_workflow.py` | ST5 run command (enrollments + exchange rates) |
| `exchange_api.py` | GET request, saving/loading the response, JSON inspection and validation |
| `integration.py` | Join by date, integrity checks, BRL conversion |
| `data/raw/st4/` | Original enrollment CSVs (simulated data, never modified) |
| `data/external/` | Real API responses saved by live runs, with metadata |
| `data/fixtures/` | Synthetic rates used for the offline demonstration and tests |
| `output/` | ST4 runs (`completed/`, `failed/`, `run_history.csv`) |
| `output/st5/` | ST5 runs (`completed/`, `failed/`, `run_history.csv`) |
| `tests/` | Test runners (`run_tests.py` for ST4, `run_tests_st5.py` for ST5) and their evidence |
| `docs/` | Project documentation, test records, AI documentation, console output of demo runs |
| `README.md` | Detailed project README (input rules, business rules, outputs, failures, limitations) |

## How to run

Requires Python 3 (tested on 3.12 and 3.13). From the `language_school_st4/` folder:

```
python -m pip install -r requirements.txt

python run_report.py                   # ST4: batch enrollment report
python run_workflow.py --mode live     # ST5: calls the real API and saves the response
python run_workflow.py --mode saved    # ST5: reuses the latest saved response (offline)
python run_workflow.py                 # ST5: synthetic demonstration data (no internet)

python tests/run_tests.py              # ST4 tests
python tests/run_tests_st5.py          # ST5 tests (local fake API, synthetic rates)
```

Exit code `0` means the run completed; `1` means it failed (the reason is printed and written to
the run's `run.log`). The last line of `output/st5/run_history.csv` shows the latest run and its
status.

## Where to read more

- `language_school_st4/README.md` - full description of ST4 and summary of ST5
- `language_school_st4/docs/st4_project_documentation.md` - ST4 documentation
- `language_school_st4/docs/st5_api_and_integration.md` - ST5 documentation (same as the PDF)
- `language_school_st4/docs/st4_test_record.md`, `st5_test_record.md` - test records
- `language_school_st4/docs/st4_ai_interaction_documentation.md`, `st5_ai_interaction_documentation.md` - AI documentation

## Notes

- The enrollment data are simulated (fictional students).
- Runs labeled `FIXTURE` use invented exchange rates; only `LIVE` and `SAVED` runs use real rates.
- The BRL conversion is a budgeting estimate, not an accounting or tax rate.
