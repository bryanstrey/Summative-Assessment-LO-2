# =========================================================
# integration.py - Join enrollments (internal) with exchange rates (external) (ST5, 5.2)
# =========================================================
# Left table  : processed enrollments (ST4)  - one row = one enrollment
# Right table : exchange rates (external)    - one row = one USD->BRL rate for one date
# Join key    : the calendar date. For enrollments it comes from the file name
#               (enrollments_YYYY-MM-DD.csv), because the files carry no date column.
# Cardinality : many enrollments -> one rate (many-to-one). The rate table must
#               have unique dates, which is checked before and after the join.
# Checks      : merge(validate="many_to_one", indicator=True) as in the ST5_2 slides.
# Matching    : same date if the provider published one; otherwise the latest
#               earlier rate within MAX_RATE_AGE_DAYS (weekends/holidays), marked
#               in column rate_match. No rate in that window = run fails.
# =========================================================

import re
from pathlib import Path

import pandas as pd

MAX_RATE_AGE_DAYS = 5
FILE_DATE_PATTERN = re.compile(r"^enrollments_(\d{4}-\d{2}-\d{2})\.csv$")
MATCH_EXACT = "same_day"
MATCH_PREVIOUS = "previous_publication_day"
BRL_SOURCE_COLUMNS = {"final_tuition": "final_tuition_brl",
                      "semester_total": "semester_total_brl",
                      "discount_amount": "discount_amount_brl"}


class IntegrationError(ValueError):
    """The join cannot be trusted. May carry the enrollments without a rate."""

    def __init__(self, message, unmatched=None):
        super().__init__(message)
        self.unmatched = unmatched


# ---------- KEY ----------

def extract_enrollment_date(file_name):
    """enrollments_2026-10-21.csv -> 2026-10-21 (the join key)."""
    found = FILE_DATE_PATTERN.match(Path(file_name).name)
    if not found:
        raise IntegrationError(
            f"Cannot read a date from the file name '{file_name}' "
            "(expected enrollments_YYYY-MM-DD.csv).")
    try:
        return pd.Timestamp(found.group(1))
    except ValueError as error:
        raise IntegrationError(f"'{file_name}' contains an impossible date.") from error


def add_join_key(processed):
    """Normalized key: a midnight-based datetime in column enrollment_date."""
    keyed = processed.copy()
    dates = {name: extract_enrollment_date(name) for name in keyed["source_file"].unique()}
    keyed["enrollment_date"] = keyed["source_file"].map(dates).astype("datetime64[ns]")
    return keyed


def check_key_uniqueness(enrollments, rates):
    """Right table: one rate per date. Left table: enrollment_id must be unique."""
    if rates["rate_date"].duplicated().any():
        raise IntegrationError("Exchange-rate table has repeated dates; the join would multiply rows.")
    if enrollments["enrollment_id"].duplicated().any():
        raise IntegrationError("Enrollment table has repeated enrollment_id values.")


# ---------- JOIN ----------

def match_rates_to_dates(dates, rates, max_age_days=MAX_RATE_AGE_DAYS):
    """One row per business date -> the rate to use (same day, else latest earlier day).

    `dates` has one row per enrollment date (the grain of the rate table), so the
    result is one rate decision per date, no matter how many enrollments it has.
    """
    right = rates[["rate_date", "rate"]].rename(columns={"rate": "fx_rate"}).copy()
    right["fx_rate_date"] = right["rate_date"]
    right["rate_date"] = right["rate_date"].astype("datetime64[ns]")
    matched = pd.merge_asof(
        dates.sort_values("enrollment_date"), right.sort_values("rate_date"),
        left_on="enrollment_date", right_on="rate_date",
        direction="backward", tolerance=pd.Timedelta(days=max_age_days))
    matched = matched.drop(columns="rate_date")
    matched["rate_match"] = "none"
    has_rate = matched["fx_rate"].notna()
    matched.loc[has_rate, "rate_match"] = MATCH_PREVIOUS
    matched.loc[has_rate & (matched["fx_rate_date"] == matched["enrollment_date"]),
                "rate_match"] = MATCH_EXACT
    if matched["enrollment_date"].duplicated().any():
        raise IntegrationError("More than one rate decision for a date.")
    return matched.reset_index(drop=True)


def attach_rates(enrollments, rates, max_age_days=MAX_RATE_AGE_DAYS):
    """Add fx_rate, fx_rate_date and rate_match to every enrollment.

    1. one row per enrollment date -> its rate (match_rates_to_dates)
    2. enrollments.merge(..., how="left", validate="many_to_one", indicator=True)
       keeps every enrollment, refuses a date with two rates, and flags a missing match.
    Enrollments with no usable rate are NOT dropped: they stay with an empty rate so
    the caller can list them and stop the run.
    """
    check_key_uniqueness(enrollments, rates)
    dates = enrollments[["enrollment_date"]].drop_duplicates()
    per_date = match_rates_to_dates(dates, rates, max_age_days)
    try:
        joined = enrollments.merge(per_date, on="enrollment_date", how="left",
                                   validate="many_to_one", indicator=True)
    except pd.errors.MergeError as error:
        raise IntegrationError(f"Unexpected relationship between enrollments and rates: {error}") from error
    joined["rate_found"] = joined["_merge"].eq("both") & joined["fx_rate"].notna()
    return joined.drop(columns="_merge").reset_index(drop=True)


def add_brl_amounts(joined):
    """Convert USD amounts to BRL row by row, rounded to centavos."""
    converted = joined.copy()
    for usd_column, brl_column in BRL_SOURCE_COLUMNS.items():
        converted[brl_column] = (converted[usd_column] * converted["fx_rate"]).round(2)
    return converted


# ---------- CHECKS ----------

def check_integration(before, after, tolerance=0.005):
    """Counts, totals and rate coverage must survive the join. Raises if not."""
    if len(after) != len(before):
        raise IntegrationError(f"Row count changed in the join: {len(before)} -> {len(after)}.")
    if list(after["enrollment_id"]) != list(before["enrollment_id"]):
        raise IntegrationError("Enrollment order or identity changed in the join.")
    usd_before = round(before["semester_total"].sum(), 2)
    usd_after = round(after["semester_total"].sum(), 2)
    if abs(usd_before - usd_after) > tolerance:
        raise IntegrationError(f"USD total changed in the join: {usd_before} -> {usd_after}.")
    missing = after[~after["rate_found"]]
    if not missing.empty:
        dates = ", ".join(sorted({f"{d:%Y-%m-%d}" for d in missing["enrollment_date"]}))
        raise IntegrationError(
            f"{len(missing)} of {len(after)} enrollments have no exchange rate within "
            f"{MAX_RATE_AGE_DAYS} days before their date ({dates}).", unmatched=missing)


def check_conversion(converted, tolerance=0.01):
    """Recompute every BRL value independently and compare."""
    for usd_column, brl_column in BRL_SOURCE_COLUMNS.items():
        expected = converted[usd_column] * converted["fx_rate"]
        worst = (converted[brl_column] - expected).abs().max()
        if worst > tolerance:
            raise IntegrationError(f"{brl_column} differs from USD x rate by {worst:.4f}.")


# ---------- SUMMARIES ----------

def summarize_rate_usage(converted):
    """One row per enrollment date: which rate was used and what it produced."""
    usage = converted.groupby(["enrollment_date", "fx_rate_date", "fx_rate", "rate_match"],
                              as_index=False).agg(
        enrollments=("enrollment_id", "count"),
        semester_revenue_usd=("semester_total", "sum"),
        semester_revenue_brl=("semester_total_brl", "sum"))
    for column in ("enrollment_date", "fx_rate_date"):
        usage[column] = usage[column].dt.strftime("%Y-%m-%d")
    # Round the money only: the rate keeps all the decimals the provider published.
    money = ["semester_revenue_usd", "semester_revenue_brl"]
    usage[money] = usage[money].round(2)
    return usage


def summarize_by_course_brl(converted):
    """Course summary in USD and BRL (same ordering rule as ST4: revenue, then name)."""
    summary = converted.groupby("course", as_index=False).agg(
        enrollments=("enrollment_id", "count"),
        semester_revenue_usd=("semester_total", "sum"),
        semester_revenue_brl=("semester_total_brl", "sum"))
    return summary.sort_values(["semester_revenue_usd", "course"],
                               ascending=[False, True]).reset_index(drop=True).round(2)
