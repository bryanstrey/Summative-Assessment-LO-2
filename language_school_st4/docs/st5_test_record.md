# ST5 Test Record

Global Languages Academy - exchange-rate integration. Authors: Bryan Strey and Victor Luis Soares Brito.

Run on 2026-11-25 20:31 with Python 3.12.5, pandas 3.1.1, requests 2.34.2.

> **What these tests prove.** The real API was not called. A local test server on this computer returned synthetic rates (invented for the tests, not market values). The tests show that the code handles normal and abnormal answers correctly. They do not show what the real Frankfurter API returns; that needs one real run (`python run_workflow.py --mode live`).

**Result: 40 of 40 tests passed.**

Expected BRL total for the normal case (hand calculation): 135044.70.

| ID | Test | Result |
|---|---|---|
| S1 | Live mode with a normal answer | PASS |
| S2 | Saved mode reuses the saved response | PASS |
| S3 | Workbook and report document the external information | PASS |
| S4 | ST4 outputs and raw data are preserved | PASS |
| S5 | Saved mode with nothing saved | PASS |
| S6 | Saved response changed after saving | PASS |
| S7 | API does not answer in time | PASS |
| S8 | HTTP 500 | PASS |
| S9 | HTTP 503 with a long Retry-After | PASS |
| S9b | A long Retry-After stops the run without retrying | PASS |
| S10 | HTTP 422 | PASS |
| S11 | Connection refused | PASS |
| S12 | Not JSON | PASS |
| S13 | JSON with another structure | PASS |
| S14 | Empty list | PASS |
| S15 | Rate is text | PASS |
| S16 | Rate is zero | PASS |
| S17 | Rate is negative | PASS |
| S18 | Missing field | PASS |
| S19 | Date is not a date | PASS |
| S20 | Wrong quote currency (EUR instead of BRL) | PASS |
| S21 | Two rates for the same date | PASS |
| S22 | Implausible rate (unit change, e.g. 520.0) | PASS |
| S23 | Valid rates that do not cover the enrollment dates | PASS |
| S24 | Enrollment on a Saturday uses Friday's rate and says so | PASS |
| S25 | File name without a date | PASS |
| S30 | Temporary 503 is retried and the run completes | PASS |
| S31 | Retries are limited to 3 attempts | PASS |
| S31b | Exactly 3 requests were sent | PASS |
| S32 | HTTP 500 is not retried | PASS |
| S32b | Exactly 1 request was sent | PASS |
| S33 | Content-Type is HTML, not JSON | PASS |
| S34 | Fixture mode runs without internet and is labeled synthetic | PASS |
| S35 | Repeated valid run: same results, new run folder | PASS |
| S36 | The run keeps a snapshot of its inputs and records the environment | PASS |
| S37 | Missing fixture fails visibly (no automatic change of mode) | PASS |
| S26 | Join keeps rows, order and totals (many enrollments -> one rate) | PASS |
| S27 | Duplicate date in the rate table is refused | PASS |
| S28 | Rate too old is not used | PASS |
| S29 | A lost row is detected | PASS |

### S1 - Live mode with a normal answer (PASS)

- **Setup:** Local fake API returns 7 synthetic rates (10-14 to 10-22); 10 enrollments in 2 files
- **Expected:** Completed; GET parameters ['from=2026-10-14', 'to=2026-10-22', 'base=USD', 'quotes=BRL', 'providers=BCB']; response + metadata saved; integrated CSV with 10 rows and BRL total 135044.70; history says live
- **Actual:** exit 0; request /v2/rates?from=2026-10-14&to=2026-10-22&base=USD&quotes=BRL&providers=BCB; saved ['frankfurter_BCB_USDBRL_2026-10-14_2026-10-22_20261125T233139.json', 'frankfurter_BCB_USDBRL_2026-10-14_2026-10-22_20261125T233139.metadata.json']; rows 10; BRL total 135044.7; history mode live

### S2 - Saved mode reuses the saved response (PASS)

- **Setup:** Same folder as S1, run again with --mode saved
- **Expected:** Completed without any request to the API; same BRL total; a second run folder; history says saved; report states SAVED mode
- **Actual:** exit 0; new requests 0; BRL 135044.7; run folders 2; mode saved

### S3 - Workbook and report document the external information (PASS)

- **Setup:** Open the workbook and report written by S1
- **Expected:** Four sheets; 10 enrollment rows; Run_Info lists provider, endpoint, parameters, acquisition time, units, use conditions, source mode (endpoint is the local test server)
- **Actual:** sheets ['Enrollments', 'By_Course', 'Exchange_Rates', 'Run_Info']; run info items ['Run ID', 'Generated', 'Source mode', 'Source mode meaning', 'Business period', 'Rates file', 'Provider', 'Endpoint', 'Parameters', 'Acquired at (UTC)', 'Rate units', 'Rates in response', 'Response SHA-256', 'Use conditions', 'Enrollment files', 'Rate matching', 'Rounding', 'Environment']; mode live

### S4 - ST4 outputs and raw data are preserved (PASS)

- **Setup:** SHA-256 of every file in output/ (ST4 results) and data/raw/st4 before and after S1-S3
- **Expected:** Identical
- **Actual:** Identical

### S5 - Saved mode with nothing saved (PASS)

- **Setup:** Empty external/ folder, --mode saved
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['No saved response'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: No saved response in tests/test_runs_st5/S5_saved_without_file/external. Run once with --mode live first.; nothing in completed/: True; nothing saved in external/: True

### S6 - Saved response changed after saving (PASS)

- **Setup:** Copy of the S1 saved response with one rate edited by hand (checksum no longer matches)
- **Expected:** Failed with a checksum message; no result files
- **Actual:** exit 1; message: frankfurter_BCB_USDBRL_2026-10-14_2026-10-22_20261125T233139.json does not match its metadata checksum (file changed after saving).

### S7 - API does not answer in time (PASS)

- **Setup:** Fake API waits 3 s; timeout set to 0.5 s
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['did not answer within', 'gave up after 3 attempts'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API did not answer within 0.5 s (http://127.0.0.1:65220/v2/rates). (gave up after 3 attempts); nothing in completed/: True; nothing saved in external/: True

### S8 - HTTP 500 (PASS)

- **Setup:** Fake API answers 500
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['HTTP 500'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API answered HTTP 500: server-side error at the provider.; nothing in completed/: True; nothing saved in external/: True

### S9 - HTTP 503 with a long Retry-After (PASS)

- **Setup:** Fake API answers 503 + Retry-After: 30 (program accepts at most 10 s)
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['HTTP 503', 'Retry-After=30', 'try again later'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API answered HTTP 503: the service is unavailable; Retry-After=30. The provider asked to wait 30 s, longer than the 10 s this program accepts; try again later.; nothing in completed/: True; nothing saved in external/: True

### S9b - A long Retry-After stops the run without retrying (PASS)

- **Setup:** Same case as S9, counting the requests the fake API received
- **Expected:** Exactly 1 request
- **Actual:** 1 request(s)

### S10 - HTTP 422 (PASS)

- **Setup:** Fake API answers 422
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['HTTP 422'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API answered HTTP 422: the provider/date-range combination was rejected.; nothing in completed/: True; nothing saved in external/: True

### S11 - Connection refused (PASS)

- **Setup:** No server listening at the address
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['Could not connect'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Could not connect to the exchange-rate API (http://127.0.0.1:65232/v2/rates): check the internet connection, a proxy or a firewall. (gave up after 3 attempts); nothing in completed/: True; nothing saved in external/: True

### S12 - Not JSON (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['not valid JSON'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Exchange-rate API: the response is not valid JSON (Expecting value: line 1 column 1 (char 0)).; nothing in completed/: True; nothing saved in external/: True

### S13 - JSON with another structure (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['expected a list'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Unexpected JSON structure: expected a list of rates, got object with keys: rates.; nothing in completed/: True; nothing saved in external/: True

### S14 - Empty list (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['no rates'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The API returned no rates for the requested period.; nothing in completed/: True; nothing saved in external/: True

### S15 - Rate is text (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['not a number'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Rate #1 (2026-10-21): 'rate' is not a number ('5.20').; nothing in completed/: True; nothing saved in external/: True

### S16 - Rate is zero (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['positive'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Rate #1 (2026-10-21): 'rate' must be a positive number (0).; nothing in completed/: True; nothing saved in external/: True

### S17 - Rate is negative (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['positive'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Rate #1 (2026-10-21): 'rate' must be a positive number (-5.2).; nothing in completed/: True; nothing saved in external/: True

### S18 - Missing field (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['lacks field'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Rate #1 lacks field(s): base, quote.; nothing in completed/: True; nothing saved in external/: True

### S19 - Date is not a date (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['YYYY-MM-DD'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Rate #1: 'date' is not YYYY-MM-DD ('21/10/2026').; nothing in completed/: True; nothing saved in external/: True

### S20 - Wrong quote currency (EUR instead of BRL) (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['Unexpected currencies'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Unexpected currencies: base USD, quote ['EUR']; expected USD->BRL (BRL per 1 USD).; nothing in completed/: True; nothing saved in external/: True

### S21 - Two rates for the same date (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['same date'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: More than one rate for the same date: 2026-10-21.; nothing in completed/: True; nothing saved in external/: True

### S22 - Implausible rate (unit change, e.g. 520.0) (PASS)

- **Setup:** Fake API answers HTTP 200 with data that is not suitable
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['Implausible'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Implausible rate 520.0 on 2026-10-21: outside 1.0-20.0 BRL per 1 USD. The unit or the provider may have changed.; nothing in completed/: True; nothing saved in external/: True

### S23 - Valid rates that do not cover the enrollment dates (PASS)

- **Setup:** Fake API returns only rates from 2026-10-01/02; enrollments are 10-21 and 10-22
- **Expected:** Failed (no rate within 5 days); incomplete result kept apart: unmatched_enrollments.csv in failed/ with 10 rows; nothing in completed/
- **Actual:** exit 1; message: 10 of 10 enrollments have no exchange rate within 5 days before their date (2026-10-21, 2026-10-22).; unmatched rows 10; completed/ empty True

### S24 - Enrollment on a Saturday uses Friday's rate and says so (PASS)

- **Setup:** File enrollments_2026-10-24.csv (Saturday); the fake API has a rate for Friday 10-23 only
- **Expected:** Completed; rate_date 2026-10-23; rate_match previous_publication_day; report says 5 of 5 used the previous rate
- **Actual:** exit 0; rate dates {'2026-10-23'}; match {'previous_publication_day'}

### S25 - File name without a date (PASS)

- **Setup:** Only enrollments_today.csv in the input folder
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['Cannot read a date'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Cannot read a date from the file name 'enrollments_today.csv' (expected enrollments_YYYY-MM-DD.csv).; nothing in completed/: True; nothing saved in external/: True

### S30 - Temporary 503 is retried and the run completes (PASS)

- **Setup:** Fake API answers 503 (Retry-After 0) once, then the normal answer
- **Expected:** Completed after exactly 2 requests; the retry is in run.log
- **Actual:** exit 0; requests 2; retry logged True

### S31 - Retries are limited to 3 attempts (PASS)

- **Setup:** Fake API always answers 503 (Retry-After 0)
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['HTTP 503', 'gave up after 3 attempts'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API answered HTTP 503: the service is unavailable; Retry-After=0. (gave up after 3 attempts); nothing in completed/: True; nothing saved in external/: True

### S31b - Exactly 3 requests were sent (PASS)

- **Setup:** Same case as S31
- **Expected:** 3 requests
- **Actual:** 3 request(s)

### S32 - HTTP 500 is not retried (PASS)

- **Setup:** Fake API answers 500
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['HTTP 500'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: The exchange-rate API answered HTTP 500: server-side error at the provider.; nothing in completed/: True; nothing saved in external/: True

### S32b - Exactly 1 request was sent (PASS)

- **Setup:** Same case as S32
- **Expected:** 1 request
- **Actual:** 1 request(s)

### S33 - Content-Type is HTML, not JSON (PASS)

- **Setup:** Fake API answers 200 with Content-Type text/html
- **Expected:** exit code 1, run filed under failed/ with a log, message mentions ['Expected JSON'], no result files and no response saved
- **Actual:** exit code 1; history status FAILED; message: Expected JSON but the API sent 'text/html'.; nothing in completed/: True; nothing saved in external/: True

### S34 - Fixture mode runs without internet and is labeled synthetic (PASS)

- **Setup:** --mode fixture with the project's synthetic fixture; the API address points to a closed port
- **Expected:** Completed; BRL total 135044.70; report says SOURCE MODE: FIXTURE and SYNTHETIC; history says fixture; nothing saved in external/
- **Actual:** exit 0; BRL 135044.7; synthetic label True; mode fixture; external []

### S35 - Repeated valid run: same results, new run folder (PASS)

- **Setup:** Run S34 a second time
- **Expected:** Two different run folders; integrated CSV files identical
- **Actual:** exit 0; folders 2; identical CSV True

### S36 - The run keeps a snapshot of its inputs and records the environment (PASS)

- **Setup:** Look inside the run folder of S34 and its workbook Run_Info
- **Expected:** source_snapshot/ holds both enrollment files, the rates file and its metadata (identical copies); Run_Info has source mode meaning, business period 2026-10-21 to 2026-10-22, environment versions
- **Actual:** snapshot files ['enrollments_2026-10-21.csv', 'enrollments_2026-10-22.csv', 'frankfurter_FIXTURE_USDBRL_2026-10-14_2026-10-22_synthetic.json', 'frankfurter_FIXTURE_USDBRL_2026-10-14_2026-10-22_synthetic.metadata.json']; input identical True; business period 2026-10-21 to 2026-10-22; environment Python 3.12.5, pandas 3.1.1, requests 2.34.2

### S37 - Missing fixture fails visibly (no automatic change of mode) (PASS)

- **Setup:** Fixture folder is empty; the fake API would have answered, but must not be used
- **Expected:** Failed with 'synthetic fixture is missing'; 0 requests to the fake API; nothing saved in external/
- **Actual:** exit 1; message: No saved response in tests/test_runs_st5/S37_missing_fixture/no_fixture_here. The synthetic fixture is missing from the project.; requests to the API: 0

### S26 - Join keeps rows, order and totals (many enrollments -> one rate) (PASS)

- **Setup:** 3 enrollments (two on 10-21, one on 10-22) and 2 rates
- **Expected:** 3 rows, same order, rates 5,5,6, USD total 600
- **Actual:** rows 3; rates [5.0, 5.0, 6.0]

### S27 - Duplicate date in the rate table is refused (PASS)

- **Setup:** Rate table with 10-21 twice (would turn 2 rows into 4)
- **Expected:** IntegrationError 'repeated dates'
- **Actual:** raised

### S28 - Rate too old is not used (PASS)

- **Setup:** Rates 30 days before the enrollments, limit 5 days
- **Expected:** Rows are kept, rate empty, IntegrationError lists 3 unmatched enrollments
- **Actual:** as expected

### S29 - A lost row is detected (PASS)

- **Setup:** Join result with one row removed
- **Expected:** IntegrationError 'Row count changed'
- **Actual:** raised
