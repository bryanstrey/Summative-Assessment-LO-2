# =========================================================
# exchange_api.py - Controlled access to an external exchange-rate API (ST5, 5.1)
# =========================================================
# Provider : Frankfurter (https://frankfurter.dev), API version 2
# Endpoint : GET {API_BASE_URL}/rates?from=&to=&base=USD&quotes=BRL&providers=BCB
# Data     : USD -> BRL daily reference rates published by the Banco Central
#            do Brasil (PTAX), relayed by Frankfurter. No API key is needed.
#
# What this module does (and nothing else):
#   - fetch_rates()           one controlled GET: parameters, timeout, HTTP errors
#   - save_response()         keep the raw response + a metadata file next to it
#   - load_saved_response()   read a saved response back and check it is intact
#   - inspect_json()          describe the JSON structure (for log and report)
#   - rates_to_dataframe()    JSON -> DataFrame with meaningful column names
#   - validate_rates()        structure, types, units, coverage checks
#
# Joining the rates to the enrollments happens in integration.py.
# =========================================================

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ---------- CONFIGURATION (every choice that could be questioned is here) ----------
API_BASE_URL = "https://api.frankfurter.dev/v2"
PROVIDER_ID = "BCB"                 # provider key from the Frankfurter providers page
PROVIDER_NAME = "Banco Central do Brasil (PTAX), relayed by Frankfurter API v2"
BASE_CURRENCY = "USD"
QUOTE_CURRENCY = "BRL"
RATE_UNITS = "BRL per 1 USD"
REQUEST_TIMEOUT = (5, 20)           # (connect, read) seconds, as in the ST5_1 slides
MAX_ATTEMPTS = 3                    # bounded retries: first try + 2 retries, temporary failures only
RETRY_DELAY_SECONDS = 2             # waiting time before retry n is n x this value
MAX_RETRY_AFTER_SECONDS = 10        # a longer Retry-After from the provider stops the run instead
RETRYABLE_STATUS = (429, 502, 503, 504)
# Sanity limit for a USD->BRL rate. This is OUR assumption (not from the provider):
# anything outside it is treated as unsuitable data, not as a real exchange rate.
PLAUSIBLE_RATE_RANGE = (1.0, 20.0)
USE_CONDITIONS = (
    "Public data, provided as is by Frankfurter; the underlying rates belong to the "
    "provider (Banco Central do Brasil) and its terms apply. Rates can be late, "
    "missing or revised. For informational budgeting only: not an accounting, tax "
    "or legal exchange rate (verify with the provider for those uses).")
DOCUMENTATION_URL = "https://frankfurter.dev/"
RESPONSE_COLUMNS = ["date", "base", "quote", "rate"]


class ExchangeRateError(ValueError):
    """The external data could not be obtained or is not suitable for use.

    Subclass of ValueError so the workflow treats it as a known failure
    (the run is stopped and filed as FAILED) rather than a program bug.
    """


# ---------- 5.1 STEP 1: CONTROLLED REQUEST ----------

def build_request(start, end, api_base_url=API_BASE_URL, provider=PROVIDER_ID):
    """The exact URL and query parameters of the GET request."""
    url = f"{api_base_url.rstrip('/')}/rates"
    params = {
        "from": start.isoformat(), "to": end.isoformat(),
        "base": BASE_CURRENCY, "quotes": QUOTE_CURRENCY, "providers": provider,
    }
    return url, params


def fetch_rates(start, end, api_base_url=API_BASE_URL, provider=PROVIDER_ID,
                timeout=REQUEST_TIMEOUT, log=None, sleep=time.sleep):
    """One GET request with a few bounded retries for temporary failures.

    Retried (GET is safe to repeat): timeout, connection failure, HTTP 429/502/503/504.
    Never retried: other HTTP errors, wrong content type, invalid JSON (those are
    not temporary). A Retry-After longer than MAX_RETRY_AFTER_SECONDS stops the run.
    Every failure becomes an ExchangeRateError a person can act on.
    """
    log = log or (lambda text: None)
    url, params = build_request(start, end, api_base_url, provider)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = RETRY_DELAY_SECONDS * attempt
        try:
            response = requests.get(url, params=params, timeout=timeout,
                                    headers={"Accept": "application/json"})
        except requests.Timeout:
            problem = f"The exchange-rate API did not answer within {timeout} s ({url})."
        except requests.ConnectionError:
            problem = (f"Could not connect to the exchange-rate API ({url}): "
                       "check the internet connection, a proxy or a firewall.")
        except requests.RequestException as error:
            raise ExchangeRateError(f"The request to {url} failed: {error}") from error
        else:
            if response.status_code == 200:
                return check_and_pack(response, url, params)
            problem = describe_http_error(response)
            if response.status_code not in RETRYABLE_STATUS:
                raise ExchangeRateError(problem)
            asked = response.headers.get("Retry-After", "")
            if asked.isdigit():
                if int(asked) > MAX_RETRY_AFTER_SECONDS:
                    raise ExchangeRateError(
                        f"{problem} The provider asked to wait {asked} s, longer than the "
                        f"{MAX_RETRY_AFTER_SECONDS} s this program accepts; try again later.")
                wait = int(asked)
        if attempt == MAX_ATTEMPTS:
            raise ExchangeRateError(f"{problem} (gave up after {attempt} attempts)")
        log(f"Attempt {attempt} failed ({problem}) - retrying in {wait} s")
        sleep(wait)


def check_and_pack(response, url, params):
    """A 200 answer must declare JSON; then keep its bytes and what was asked."""
    kind = response.headers.get("Content-Type", "")
    if "application/json" not in kind.lower():
        raise ExchangeRateError(f"Expected JSON but the API sent '{kind or 'no content type'}'.")
    return {
        "content": response.content,
        "url": url,
        "params": params,
        "http_status": response.status_code,
        "acquired_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def describe_http_error(response):
    """Plain-language message for a non-200 answer."""
    code = response.status_code
    if code == 422:
        hint = "the provider/date-range combination was rejected"
    elif code == 429:
        hint = "too many requests; wait before trying again"
    elif code == 503:
        retry = response.headers.get("Retry-After")
        hint = "the service is unavailable" + (f"; Retry-After={retry}" if retry else "")
    elif 400 <= code < 500:
        hint = "the request was not accepted (check the parameters)"
    else:
        hint = "server-side error at the provider"
    return f"The exchange-rate API answered HTTP {code}: {hint}."


def parse_json(content, origin):
    """Bytes -> Python object, or a clear error if it is not JSON."""
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExchangeRateError(f"{origin}: the response is not valid JSON ({error}).") from error


# ---------- 5.1 STEP 2: INSPECT, DATAFRAME, VALIDATE ----------

def inspect_json(payload):
    """Short description of the JSON structure, for the log and the report."""
    if isinstance(payload, list):
        first = payload[0] if payload else None
        fields = (", ".join(f"{key}:{type(value).__name__}" for key, value in first.items())
                  if isinstance(first, dict) else "n/a")
        return f"list with {len(payload)} item(s); first item fields: {fields}"
    if isinstance(payload, dict):
        return "object with keys: " + ", ".join(payload)
    return f"{type(payload).__name__} (not the expected list of rates)"


def rates_to_dataframe(payload):
    """JSON list of {date, base, quote, rate} -> DataFrame with readable names.

    Columns: rate_date (datetime), base_currency, quote_currency, rate (float).
    Anything that does not look like that raises ExchangeRateError.
    """
    if not isinstance(payload, list):
        raise ExchangeRateError(
            "Unexpected JSON structure: expected a list of rates, got "
            f"{inspect_json(payload)}.")
    if not payload:
        raise ExchangeRateError("The API returned no rates for the requested period.")

    records = []
    for position, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ExchangeRateError(f"Rate #{position} is not an object.")
        missing = [name for name in RESPONSE_COLUMNS if name not in item]
        if missing:
            raise ExchangeRateError(f"Rate #{position} lacks field(s): {', '.join(missing)}.")
        value = item["rate"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExchangeRateError(
                f"Rate #{position} ({item['date']}): 'rate' is not a number ({value!r}).")
        if not math.isfinite(value) or value <= 0:
            raise ExchangeRateError(
                f"Rate #{position} ({item['date']}): 'rate' must be a positive number ({value!r}).")
        try:
            rate_date = datetime.strptime(str(item["date"]), "%Y-%m-%d")
        except ValueError as error:
            raise ExchangeRateError(
                f"Rate #{position}: 'date' is not YYYY-MM-DD ({item['date']!r}).") from error
        records.append({"rate_date": rate_date, "base_currency": item["base"],
                        "quote_currency": item["quote"], "rate": float(value)})

    rates = pd.DataFrame(records)
    rates["rate_date"] = rates["rate_date"].astype("datetime64[ns]")
    return rates.sort_values("rate_date").reset_index(drop=True)


def validate_rates(rates, base=BASE_CURRENCY, quote=QUOTE_CURRENCY,
                   plausible=PLAUSIBLE_RATE_RANGE):
    """Check meaning (units), uniqueness and plausibility of the rates."""
    wrong_base = rates.loc[rates["base_currency"] != base, "base_currency"].unique()
    wrong_quote = rates.loc[rates["quote_currency"] != quote, "quote_currency"].unique()
    if len(wrong_base) or len(wrong_quote):
        raise ExchangeRateError(
            f"Unexpected currencies: base {list(wrong_base) or base}, "
            f"quote {list(wrong_quote) or quote}; expected {base}->{quote} ({RATE_UNITS}).")
    repeated = rates.loc[rates["rate_date"].duplicated(), "rate_date"]
    if not repeated.empty:
        raise ExchangeRateError(
            "More than one rate for the same date: "
            + ", ".join(f"{d:%Y-%m-%d}" for d in repeated.unique()) + ".")
    low, high = plausible
    outside = rates[(rates["rate"] < low) | (rates["rate"] > high)]
    if not outside.empty:
        sample = outside.iloc[0]
        raise ExchangeRateError(
            f"Implausible rate {sample['rate']} on {sample['rate_date']:%Y-%m-%d}: outside "
            f"{low}-{high} {RATE_UNITS}. The unit or the provider may have changed.")
    return rates


def describe_coverage(rates):
    """Facts about the period actually covered (reported, not assumed)."""
    return {"count": len(rates),
            "first_date": rates["rate_date"].min().strftime("%Y-%m-%d"),
            "last_date": rates["rate_date"].max().strftime("%Y-%m-%d"),
            "min_rate": float(rates["rate"].min()), "max_rate": float(rates["rate"].max())}


# ---------- 5.1 STEP 3: SAVE THE RESPONSE WITH ITS METADATA ----------

def sha256_of(content):
    return hashlib.sha256(content).hexdigest()


def build_metadata(fetched, coverage, structure):
    """Everything needed to understand the saved response later."""
    return {
        "provider": PROVIDER_NAME,
        "provider_key": PROVIDER_ID,
        "endpoint": fetched["url"],
        "parameters": fetched["params"],
        "http_status": fetched["http_status"],
        "acquired_at": fetched["acquired_at"],        # UTC
        "units": RATE_UNITS,
        "base_currency": BASE_CURRENCY,
        "quote_currency": QUOTE_CURRENCY,
        "use_conditions": USE_CONDITIONS,
        "documentation": DOCUMENTATION_URL,
        "response_structure": structure,
        "rates_count": coverage["count"],
        "first_rate_date": coverage["first_date"],
        "last_rate_date": coverage["last_date"],
        "response_sha256": sha256_of(fetched["content"]),
        "requests_version": requests.__version__,
    }


def save_response(content, metadata, external_dir):
    """Write response and metadata. Existing files are never overwritten."""
    external_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(metadata["acquired_at"]).strftime("%Y%m%dT%H%M%S")
    params = metadata["parameters"]
    stem = (f"frankfurter_{params['providers']}_{params['base']}{params['quotes']}_"
            f"{params['from']}_{params['to']}_{stamp}")
    data_path = external_dir / f"{stem}.json"
    meta_path = external_dir / f"{stem}.metadata.json"
    with data_path.open("xb") as file:
        file.write(content)
    with meta_path.open("x", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return data_path, meta_path


def list_saved_responses(external_dir):
    """Saved response files, oldest first (the name carries the acquisition time)."""
    if not external_dir.is_dir():
        return []
    return sorted(path for path in external_dir.glob("frankfurter_*.json")
                  if not path.name.endswith(".metadata.json"))


def load_saved_response(data_path):
    """Read a saved response and its metadata; refuse a file that was altered."""
    meta_path = data_path.with_name(data_path.stem + ".metadata.json")
    if not data_path.is_file():
        raise ExchangeRateError(f"Saved response not found: {data_path.name}.")
    if not meta_path.is_file():
        raise ExchangeRateError(f"Metadata file missing for {data_path.name}.")
    content = data_path.read_bytes()
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExchangeRateError(f"{meta_path.name} is not valid JSON ({error}).") from error
    if metadata.get("response_sha256") != sha256_of(content):
        raise ExchangeRateError(
            f"{data_path.name} does not match its metadata checksum (file changed after saving).")
    return content, metadata
