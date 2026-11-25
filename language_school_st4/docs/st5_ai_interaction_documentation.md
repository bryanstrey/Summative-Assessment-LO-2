# ST5 AI Interaction Documentation
## Global Languages Academy - Exchange-Rate API, Data Integration and Workflow

**Students:** Bryan Strey, Victor Luis Soares Brito

**AI tool and version:** Claude Sonnet 5.5 (`claude-sonnet-5-5`, Anthropic), used as a coding agent with file, shell and web tools, 24 November 2026. The model actually serving a turn may differ from the configured one; this is the configured model.

This document records, for the ST5 work: the prompt used, the relevant AI response and the suggestions considered, the changes accepted or rejected and why, the test used to verify each adopted change, the observed result, and the remaining limitations. Earlier interactions are in the ST1/ST2 and ST4 AI documents.

*Note on the prompts:* the prompts are written out in full, including context established earlier in the conversation. The original chat message was much shorter (it was a screenshot of the ST4 and ST5 grading criteria plus the text file listing the ST4 and ST5 deliverables, with the sentence "these files have this here" in Portuguese). In this first round the ST5 course slides were **not** given to the AI; it worked only from the criteria and the deliverable list. The slides were given in a second round (section 2).

---

## 1. Building the ST5 extension

**Prompt:** *"Here are the grading criteria for ST4 (4.1 to 4.4) and ST5 (5.1 to 5.4), and the text file with the list of ST4 and ST5 deliverables. Check whether our ST4 project already satisfies the ST4 criteria, and build ST5 on top of it: call an external API with a controlled GET request, save the response with its metadata, put the JSON into a DataFrame and validate it, join the external data with our enrollment data, and turn everything into a simple workflow with one documented command, an integrated CSV, an updated workbook, a report, logs, and an AI interaction document. Do not change the ST4 deliverables. Keep the documents in English. Be honest about what was and was not verified."*

**AI response:** The AI compared ST4 with the criteria and reported one gap (the ST3 logic was never provided, so it was not reused). It tried three exchange-rate hosts from its sandbox; all were refused by the network proxy, so it **did not fabricate any API data** and built live and saved modes, tested against a local server. It wrote `exchange_api.py`, `integration.py`, `run_workflow.py`, `tests/run_tests_st5.py`, and the ST5 documents.

### Suggestions considered

| # | Suggestion | Decision and reason | Verification | Observed result |
|---|---|---|---|---|
| A1 | Business question: projected semester revenue in BRL, using the USD→BRL rate of each enrollment date | **Accepted as a project assumption.** The school prices in USD; a manager in Brazil needs BRL. *Not adopted:* inventing a second dataset just to have something to join | Section 1 of the ST5 document; the team can change it | Needs the team's confirmation. *Limitation:* "manager budgets in BRL" is an assumption |
| A2 | Use the free Frankfurter API v2 | **Accepted.** No key, documented JSON format. *Not adopted:* v1 (deprecated; response format not documented on the page read) and two other hosts (blocked) | Documentation read by the AI; code never ran against the real host | **Unverified against the real API** |
| A3 | Request provider `BCB` (Banco Central do Brasil) | **Accepted.** *Not adopted:* default blend (its documentation says it is not an official rate) and `ECB` (EUR-based, USD→BRL would be a cross rate) | Plausible-range check (1-20 BRL per USD) guards the unit; test S22 | Passes on synthetic data. *Limitation:* BCB's quotation convention is not stated on the page |
| A4 | Save the raw response and a metadata file; checksum it; never overwrite | **Accepted** (required by 5.1) | S1 (files created), S6 (edited file rejected) | Pass |
| A5 | Save only after validation | **Accepted.** Invalid data should not become a "saved source" | S12-S22: external folder stays empty | Pass |
| A6 | Join by date from the file name with `merge_asof` (same day, else earlier rate within 5 days), mark `rate_match` | **Accepted.** Weekends have no rate. *Not adopted:* exact `merge`, which would fail every weekend; and filling forward without a limit | S24 (Saturday), S23 (no rate), S26 | Pass. *Limitation:* tolerance of 5 days is our assumption |
| A7 | Fail the run if any enrollment has no rate, and write `unmatched_enrollments.csv` in the failed folder | **Accepted.** *Not adopted:* dropping those rows (would change totals silently) | S23, S28 | Pass |
| A8 | Test the live mode against a local fake API with synthetic rates | **Accepted** because the real API was unreachable. *Not adopted:* saving a hand-written "sample response" in `data/external/` as if real | S1-S37 | All tests pass (29 at this stage, 40 after round 2). *Limitation:* proves the code logic only, not the real API |
| A9 | Reuse the ST4 code by importing it, and write ST5 results to `output/st5/` | **Accepted** so earlier outputs stay untouched | S4 (SHA-256 before/after) | Identical |
| A10 | Write `--api-base-url` and `--timeout` options | **Accepted** for tests; defaults are the real values | S7 (timeout), S1 (URL) | Pass |

### What went wrong and was fixed

- First run of the ST5 tests: **28 of 29 passed**. S6 (tampered saved file) failed with exit code 0. The cause was the test, not the program: it replaced the text `5.2000`, but the saved JSON contains `5.2`, so the file was not changed. The test was corrected and now asserts that the file really changed before running. After this, 29 of 29 passed.

### Declaration and limits of the AI help

- The AI wrote the code and documents; the students are responsible for understanding them. Each student must be able to explain: what the GET request sends, why the response is saved after validation, why the join key comes from the file name, what `merge_asof` does and why, and why a run fails instead of skipping unmatched rows.
- The AI could not call the real API. Every statement about the real response is from documentation.

---

## 2. Second round: review against the ST5 slides

**Prompt:** *"I am sending the slides of the ST4 and ST5 lessons (API Integration, Data Acquisition and Integration, Simple Workflow Design). Compare what you built for ST5 with what the slides teach and require, and adjust the project where it differs. Keep the ST4 files unchanged and tell me honestly what is still not verified."*

**AI response:** The AI extracted the text of the three ST5 decks and listed the differences between its first version and the slides. The rubric does not ask for the HTML-extraction part of the second deck, so it was not built.

### Suggestions considered

| # | Suggestion (from the slides) | Decision and reason | Verification | Observed result |
|---|---|---|---|---|
| B1 | Add a `fixture` mode with clearly labeled synthetic data, default for the command; keep `live` and `saved` | **Accepted.** The slides separate live response, saved snapshot and synthetic fixture and ask to label the mode in every output. It also gives the team runnable demonstration outputs without internet. *Not adopted:* any automatic switch between modes (slide: "do not change modes automatically") | S34 (fixture runs offline, labeled), S37 (missing fixture fails, API not used), S2 | Pass. *Limitation:* fixture rates are invented; BRL amounts in the demonstration are not real |
| B2 | Separate connect and read timeouts (5, 20) and a `Content-Type` check | **Accepted** as shown in the slides | S7 (timeout), S33 (HTML content type) | Pass |
| B3 | Bounded retries only for temporary failures, respecting `Retry-After` | **Accepted** (max 3 attempts; 429/502/503/504, timeout, connection failure; stop if Retry-After > 10 s). *Not adopted:* retrying HTTP 500 or validation errors (not temporary) | S30 (retry then success), S31/S31b (exactly 3 requests), S9/S9b (long Retry-After: 1 request), S32/S32b (500: 1 request) | Pass. *Limitation:* the delay values (2 s, 10 s) are our choice |
| B4 | Aggregate to the grain of the external table and join with `validate=` and `indicator=True` | **Accepted.** The first version used one `merge_asof` over all enrollments, which cannot validate the relationship. Now: one row per date, one rate decision per date, then a left `many_to_one` merge with indicator. *Not adopted:* an inner join (hides missing matches) | S23 (no rate), S26-S29 (join checks), S1/S34 (totals equal the hand calculation) | Pass; BRL total unchanged (135 044.70) |
| B5 | Acquisition time in UTC; keep a copy of the raw response and of the local inputs with each run | **Accepted** (`source_snapshot/` in every completed run; metadata time in UTC) | S36 (snapshot files identical to the originals) | Pass |
| B6 | Record business period and environment versions in the outputs | **Accepted** | S36 (Run_Info) | Pass |
| B7 | Workflow tests from the slides: valid fixture, wrong unit, duplicate key, simulated timeout, repeated run | **Accepted**; all were already covered or added | S12-S22, S7, S35 (repeated run: same CSV, new folder) | Pass |

### What went wrong and was fixed in round 2

- Two of my own new tests were wrong at first: S36 expected 5 files in the snapshot but there are 4 (2 enrollment files + rates + metadata), and S37 claimed "0 requests" without measuring. Both were corrected (S37 now counts the requests the fake API received). The final run is 40 of 40.
- The first version's documents said ST5 was tested on Python 3.12; the ST5 tests ran on Python 3.13.18. The documents were corrected.

### Still not verified

The real API, the real JSON, the BCB quotation convention and the live behavior of the retry logic against the real provider.

---

## 3. Team verification

Environment: macOS, Python 3.12.5, pandas 3.1.1, openpyxl 3.1.5, requests 2.34.2 (virtual environment created with `python3 -m venv .venv` and `pip install -r requirements.txt`).

| Item | Result |
|---|---|
| Date and time of the first live run | 25 Nov 2026, 20:30:57 (UTC-3); acquisition 2026-11-25T23:30:58 UTC. Run `20261125_203057_017829` |
| Command and exit code | `python run_workflow.py --mode live` → exit 0, `COMPLETED (live mode): 10 enrollments`. HTTP 200, 441 bytes, no retry needed |
| Observed JSON structure (see the metadata file) | `list with 7 item(s); first item fields: date:str, base:str, quote:str, rate:float`, e.g. `{"date":"2026-10-21","base":"USD","quote":"BRL","rate":5.0277}`. Same as the documented structure |
| Rates received (count, first and last date) | 7 rates, 2026-10-14 to 2026-10-22 (no rates on 17-18 Oct, a weekend). Range 5.0140-5.0826 BRL per USD, inside the 1-20 check. `providers=BCB` works for these dates |
| Did every enrollment find a rate? Any `previous_publication_day`? | Yes, all 10. All `same_day`: 21 Oct → 5.0277 (5 enrollments), 22 Oct → 5.0383 (5 enrollments). No `previous_publication_day` |
| Real projected revenue in BRL (report) | USD 25 845.00 = **BRL 130 078.86** (21 Oct: USD 12 831.00 = BRL 64 510.42; 22 Oct: USD 13 014.00 = BRL 65 568.44). By course: English BRL 50 506.09, French BRL 40 660.24, Spanish BRL 38 912.53. Hand check: 12 831.00 × 5.0277 = 64 510.42 and 13 014.00 × 5.0383 = 65 568.44 |
| Anything that differed from this document | (1) In the first live run the CSV and report showed the rate rounded to 2 decimals (5.03 / 5.04), while the BRL amounts used the full rate, so USD × the printed rate did not match the BRL column. Fixed in `integration.summarize_rate_usage` and `run_workflow.write_integrated_csv`, plus a new read-back check of the CSV rate; 40 of 40 tests passed again; live mode was run again (run `20261125_203148_552931`, exit 0, same 7 rates, same totals, rate shown as 5.0277 / 5.0383). The first run's folder is kept as evidence. (2) The runs used Python 3.12.5, not 3.13.18. (3) The synthetic test rates (5.20 / 5.25) were higher than the real ones, so the real BRL total (130 078.86) is lower than the test total (135 044.70), as expected |
| Saved-mode run worked offline? | Yes. `python run_workflow.py --mode saved` with the network blocked (proxy set to an unreachable address) → exit 0, run `20261125_203151_244041`, rates file `frankfurter_BCB_USDBRL_2026-10-14_2026-10-22_20261125T233150.json`, checksum verified, same BRL 130 078.86 |

**Assumptions confirmed by the team:** BCB (Banco Central do Brasil, PTAX) as the rate provider and BRL as the manager's budget currency.
