# ST5 - API Integration, Data Integration and Simple Workflow

**Project:** Global Languages Academy - enrollments with exchange rates
**Course:** AI-Assisted Python for Business Problem Solving (Prof. Evandro Zatti)
**Students:** Bryan Strey, Victor Luis Soares Brito

> **Status of the evidence - read first.**
> The code was first written in a sandbox without internet, so it was built and tested against a local
> fake API with *synthetic* rates (all tests still use them, and the fixture demonstration is labeled
> that way). On **25 November 2026** the real API was called on the team's computer:
> `python run_workflow.py --mode live` (run `20261125_203148_552931`) and then `--mode saved` offline (run `20261125_203151_244041`),
> both COMPLETED. The real response and its metadata are in `data/external/`. The real JSON structure
> matched the provider's documentation (section 2.3). The design follows the three ST5 slide decks
> (API Integration, Data Acquisition and Integration, Simple Workflow Design).

---

## 1. Business question and why external data is needed

The school sets tuition in **USD** (ST2/ST4). The manager budgets in **Brazilian reais (BRL)**
(*assumption of this project*). The question is:

> **What is the projected semester revenue of the enrolled students in BRL, using the USD→BRL rate of
> the day each enrollment batch was registered?**

The school's own files cannot answer it: they contain no exchange rate. An external daily rate is
needed. The result is an estimate for budgeting, not an accounting figure.

## 2. The external API (rubric 5.1)

| Item | Value |
|---|---|
| Provider | Frankfurter (frankfurter.dev), API version 2 |
| Data source behind it | Banco Central do Brasil, PTAX closing rate (provider key `BCB`) |
| Endpoint | `GET https://api.frankfurter.dev/v2/rates` |
| Parameters | `from`, `to` (dates), `base=USD`, `quotes=BRL`, `providers=BCB` |
| Key / login | None required (according to the provider documentation) |
| Timeout | 5 s to connect, 20 s to read (`REQUEST_TIMEOUT`, as in the ST5_1 slides) |
| Unit | BRL per 1 USD |

**Why this API.** Free, no key, documented response format (OpenAPI), and it offers the central bank
of Brazil as a provider. **Why `BCB` and not the default.** Without `providers`, Frankfurter returns
its own blend of providers, which its documentation describes as not being an official rate. `ECB`
rates are EUR-based, so USD→BRL would be a cross rate. `BCB` is the Brazilian reference and fits a
budget in BRL. **Not verified:** whether the provider quotes USD/BRL directly and how the quotation
convention is defined; the page does not say. For this reason the code does not trust the unit - it
checks that every rate falls in a plausible BRL-per-USD range (1 to 20; our own assumption).
To use another provider, change `PROVIDER_ID` in `exchange_api.py` only.

### 2.0 Source record (ST5_2 slides)

| Item | Record |
|---|---|
| Purpose | Convert the school's USD revenue to BRL for budgeting |
| Origin | Frankfurter API v2 (provider key `BCB`, Banco Central do Brasil PTAX); endpoint above; access date and time (UTC) stored in the metadata of every saved response |
| Meaning | One record = one USD→BRL rate for one calendar date; key = `date`; unit = BRL per 1 USD; coverage = the dates requested (first enrollment date minus 7 days to last enrollment date). Timezone of the publication time: **not stated on the pages read** |
| Use conditions | Public data "as is"; provider terms apply; not an accounting/tax/legal rate; no key; no numeric rate limit stated |
| Limitations | Rates may be late, missing or revised; no rate on weekends/holidays; BCB quotation convention unverified; our 1-20 plausibility range is an assumption |

### 2.1 Controlled GET request (`exchange_api.fetch_rates`)

- Parameters are passed as a dictionary (not pasted into the URL) and are recorded in the metadata.
- The request period is from **7 days before the first enrollment date** to the last enrollment date.
  The extra days exist because a weekend or holiday has no published rate, and the provider's range
  response starts with the latest earlier rate.
- `timeout` is always set (connect and read separately). Without it, `requests` could wait forever.
- The answer must declare `Content-Type: application/json` and contain valid JSON.
- Errors become one clear exception, `ExchangeRateError`:

| Situation | What the code does |
|---|---|
| No answer in time, no connection, HTTP 429/502/503/504 | **bounded retry**: at most 3 attempts, waiting 2 s, 4 s (or the provider's `Retry-After`); each retry is logged; after the last attempt the run fails "gave up after 3 attempts" (S7, S11, S30, S31) |
| `Retry-After` longer than 10 s | stop at once: "try again later" (S9, S9b) |
| HTTP 422, other 4xx, 500 (not temporary) | no retry; message with the status code and a hint (S8, S10, S32) |
| Content-Type is not JSON, or body is not JSON | no retry; message "Expected JSON" / "not valid JSON" (S12, S33) |

### 2.2 Saved response and metadata (`save_response`)

After a live answer is validated, two files are written to `data/external/`, never overwriting
(`mode="xb"`); the name contains the acquisition time:

- `frankfurter_BCB_USDBRL_<from>_<to>_<yyyymmddThhmmss>.json` - the **raw bytes** of the response.
- `….metadata.json` - provider, endpoint, request parameters, HTTP status, **acquisition date/time**,
  **units**, **use conditions**, documentation link, JSON structure, number of rates, first/last rate
  date, SHA-256 of the response, `requests` version.

A response that fails validation is **not** saved, so the folder only contains data that was suitable.

### 2.3 Inspecting the JSON (`inspect_json`)

The documented structure is a **list of objects**, each `{"date", "base", "quote", "rate"}`
(*from the provider's documentation; **confirmed** by the real response of 25 Nov 2026:
`list with 7 item(s); first item fields: date:str, base:str, quote:str, rate:float`*). The program logs the
observed structure on every run (for example: `list with 7 item(s); first item fields: date:str,
base:str, quote:str, rate:float`) and stores it in the metadata, so the real structure is recorded
the first time the team runs live mode.

### 2.4 DataFrame and validation (`rates_to_dataframe`, `validate_rates`)

Columns: `rate_date` (datetime), `base_currency`, `quote_currency`, `rate` (float), sorted by date.

| Check | Rejects |
|---|---|
| Structure | JSON that is not a list, empty list, item without `date`/`base`/`quote`/`rate` |
| Types | `rate` that is text, boolean, NaN/infinite; date not `YYYY-MM-DD` |
| Value | `rate` ≤ 0 |
| Units / meaning | base ≠ USD or quote ≠ BRL; rate outside 1–20 BRL per USD |
| Uniqueness | two rates for the same date |
| Coverage | reported (first/last date, count); enforced per enrollment date in the join (section 3) |

**How the program reacts to unsuitable external data:** it stops, saves nothing, produces no result
files, files the run under `output/st5/failed/<run_id>/` with a log, writes a line in
`run_history.csv` with status FAILED and the reason, and returns exit code 1. It never replaces bad
data with a guess. Tests S7–S25 cover each case.

## 3. Data integration (rubric 5.2)

Following the ST5_2 slides, the join is validated (`validate=`, `indicator=True`) and the date is
the common grain: enrollments are reduced to **one row per enrollment date**, one rate decision is made
for each date, and the decision is attached to the enrollments with `many_to_one`.

| | Internal table | External table |
|---|---|---|
| Source | ST4 processed enrollments | Exchange-rate response |
| **One row means** | one enrollment of one student in one course | one USD→BRL rate for one date |
| Size in the demo | 10 rows | 7 rows (synthetic fixture) |
| Key column | `enrollment_id` (unique) | `rate_date` (unique) |

- **Join key.** The calendar date. Enrollments carry no date column, so it is taken from the file name
  `enrollments_YYYY-MM-DD.csv` (`integration.extract_enrollment_date`). It is normalized to midnight
  datetimes on both sides so `2026-10-21` always compares with `2026-10-21`. A file name without a date
  stops the run.
- **Uniqueness.** Checked before the join: no repeated `rate_date`, no repeated `enrollment_id`.
  A repeated date on the right would multiply enrollment rows (S27).
- **Cardinality.** Many enrollments → one rate (many-to-one). Every enrollment keeps exactly one rate.
- **Join type.** `pd.merge_asof(direction="backward", tolerance=5 days)` on the unique dates (same day
  if a rate exists for it, otherwise the latest earlier rate within 5 days: weekends/holidays), then
  `enrollments.merge(..., how="left", validate="many_to_one", indicator=True)`. A left join is used so
  a missing match is visible and no enrollment disappears. `rate_match` says which happened
  (`same_day` or `previous_publication_day`) and `fx_rate_date` shows the rate's own date.
- **Missing matches.** An enrollment with no usable rate is not silently dropped. The run **fails**,
  and `unmatched_enrollments.csv` is written in the failed run folder (S23).
- **Preserved counts and totals.** After the join the program checks: same number of rows, same
  `enrollment_id` order, same USD total. Then each BRL value is recomputed independently as USD × rate
  (S26, S29). The written CSV and workbook are read back and their totals compared again.
- **Traceability.** Every integrated row has `source_file`, `source_line`, `enrollment_date`,
  `fx_rate_date`, `fx_rate`, `rate_match`. The workbook sheet `Exchange_Rates` shows which rate fed
  which enrollment date. `Run_Info` and the report name the rates file and its SHA-256. Each run folder also holds `source_snapshot/`: exact copies of the enrollment files, the rates response and its metadata used by that run.

New columns: `final_tuition_brl`, `semester_total_brl`, `discount_amount_brl` = USD value × rate,
rounded to centavos **per row**; totals are sums of rounded rows.

## 4. The simple workflow (rubric 5.3)

**One command** (from the project folder; in VS Code, the terminal of the project):

```
python run_workflow.py                 # same as --mode fixture: synthetic demonstration data, no internet
python run_workflow.py --mode live     # calls the API, validates, saves the answer in data/external/
python run_workflow.py --mode saved    # reuses the latest saved real answer
```

Three kinds of external input are kept apart, as in the ST5_3 slides:

| Mode | What the rates are | Labeled in outputs as |
|---|---|---|
| `live` | bytes returned by the real service in this run | LIVE |
| `saved` | bytes preserved from an earlier live run, checksum verified | SAVED |
| `fixture` | **invented** numbers in `data/fixtures/` for demonstration and tests | FIXTURE + a warning line "amounts in BRL are NOT real" |

If a mode fails, the run fails visibly; the program never switches to another mode on its own (S37).

| Step | Function | File |
|---|---|---|
| Select, read, validate and price enrollments | `select_input_files`, `load_batch`, `process_enrollments` (ST4, reused unchanged) | `run_report.py` |
| Request / save / load rates | `fetch_rates` (with bounded retries), `save_response`, `load_saved_response`, `acquire_live`, `acquire_saved` (saved and fixture) | `exchange_api.py`, `run_workflow.py` |
| Inspect, convert, validate | `inspect_json`, `rates_to_dataframe`, `validate_rates` | `exchange_api.py` |
| Join and check | `add_join_key`, `match_rates_to_dates`, `attach_rates`, `check_integration`, `add_brl_amounts`, `check_conversion` | `integration.py` |
| Summaries | `summarize_by_course_brl`, `summarize_rate_usage` | `integration.py` |
| Write and verify outputs, report | `snapshot_sources`, `write_integrated_csv`, `write_workbook`, `verify_outputs`, `make_report_text` | `run_workflow.py` |
| Orchestrate, log, file the run | `main` | `run_workflow.py` |

**Outputs** (`output/st5/completed/<run_id>/`):

| File | Content |
|---|---|
| `integrated_enrollments.csv` | the integrated table (10 rows in the demo) |
| `enrollment_workbook_st5.xlsx` | sheets `Enrollments`, `By_Course` (USD and BRL), `Exchange_Rates`, `Run_Info` |
| `source_snapshot/` | copies of the exact inputs of the run (enrollment files, rates file, metadata) |
| `enrollment_report.txt` | what the external data is, results, checks passed, limitations, **source mode** and business period |
| `run.log` | timestamped steps, warnings, errors |

**Rules.** Incomplete results never appear in `completed/`; a failed run leaves only its log (and
`unmatched_enrollments.csv` when relevant) in `failed/`. Each run has its own folder and files are
created with exclusive mode, so nothing is overwritten. ST4 results live in `output/` and ST5 results in
`output/st5/`: earlier outputs are preserved (test S4 compares SHA-256 before/after). The **source
mode** (`live` or `saved`) is written in the log, report, workbook `Run_Info` and `run_history.csv`.

## 5. Results of the tests (synthetic rates)

40 checks, all passed in the last run (`docs/st5_test_record.md`). They follow the test list of the
ST5_3 slides: valid synthetic data with known totals (USD 25 845.00 × synthetic rates 5.20 and 5.25 =
BRL 135 044.70, equal to the hand calculation), missing date / wrong unit, duplicate key, simulated
timeout, and a repeated valid run (same results in a new folder). They also cover HTTP errors, bounded
retries, wrong content type, weekends, a missing rate, tampered saved files and preservation of ST4
results. In the first round of tests one test (S6) failed because **the test itself** did not change
the file it meant to tamper with; it was fixed. After the slides were read, the code was adjusted (modes,
retries, validated join) and the tests extended; a wrong file count in test S36 was corrected and S37
was strengthened to count requests.

Demonstration runs stored in the project (`output/st5/`, console text in `docs/st5_demo_runs_console.txt`):
a COMPLETED fixture run and a FAILED saved-mode run (no real response saved yet), so both outcomes are visible.

**Real runs (25 Nov 2026, Python 3.12.5, pandas 3.1.1, requests 2.34.2).** Live mode received 7 BCB
rates (2026-10-14 to 2026-10-22); both enrollment dates had a same-day rate (21 Oct: 5.0277; 22 Oct:
5.0383 BRL per USD). Result: **USD 25 845.00 = BRL 130 078.86** (21 Oct: BRL 64 510.42; 22 Oct:
BRL 65 568.44). Check by hand: 12 831.00 × 5.0277 + 13 014.00 × 5.0383 = 64 510.42 + 65 568.44 (row
rounding gives the same totals). Saved mode reproduced the same numbers with the network blocked.
The first live run (`20261125_203057_017829`) showed a display defect: the CSV and the report printed the rate with
2 decimals (5.03 / 5.04), although the BRL amounts were computed with the full rate. It was fixed
(the CSV keeps 4 decimals, the rate sheet is no longer rounded, and the read-back check now compares
the CSV rate with the rate used); the 40 tests passed again and live mode was run again (`20261125_203148_552931`).
The first run's folder is kept unchanged as evidence.

## 6. What was not verified

- The real API was called on two occasions on the same day only; its behaviour over time
  (late or revised rates, outages, the real retry path) was not observed.
- The BCB quotation convention (direct USD/BRL or derived) is not stated on the provider page.
- The 1–20 range and the 5-day tolerance are our assumptions.
- ST5 was tested on Python 3.13.18 (pandas 3.0.5, openpyxl 3.1.5, requests 2.34.2) and on
  Python 3.12.5 (pandas 3.1.1, openpyxl 3.1.5, requests 2.34.2), where the real runs were made.
  Other versions were not tested.
- Passing the tests does not prove that the provider is available (the slides say the same): a separate
  live check is needed.
- Behaviour on a blocked network was tested only with a local server that refuses connections.
- `output/st5/completed/` holds both the fixture demonstration (synthetic, labeled FIXTURE) and the
  real live/saved runs (labeled LIVE / SAVED); check the source mode before reading a result.

## 7. Assumptions that can be changed

BRL as the manager's budget currency; the provider key (`PROVIDER_ID`); the enrollment date coming from
the file name; the 5-day tolerance (`MAX_RATE_AGE_DAYS`); the rate range (`PLAUSIBLE_RATE_RANGE`).

## 8. How to repeat the real runs (done on 25 Nov 2026)

1. `python -m pip install -r requirements.txt`
2. `python run_workflow.py --mode live` - creates the real response in `data/external/` and a
   real run in `output/st5/completed/`.
3. `python run_workflow.py --mode saved` - shows that the saved answer works offline.
4. Open `data/external/*.metadata.json` and check the recorded structure and units.
   If the step fails, the message and `output/st5/failed/<run_id>/run.log` say why.
5. The results are recorded in the "Team verification" section of `docs/st5_ai_interaction_documentation.md`.
