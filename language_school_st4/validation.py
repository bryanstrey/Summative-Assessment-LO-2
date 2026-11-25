# =========================================================
# validation.py - Cleaning and validation of enrollment files
# =========================================================
# Every rule raises ValueError with the file name and the CSV line
# numbers (header = line 1) so the person fixing the file knows
# exactly where to look.
#
# Rule 1  Structure   - exact expected columns, at least one data row.
#         Why: a missing or renamed column would shift or drop information.
# Rule 2  Required text - enrollment_id and student_name not blank.
#         Why: each record must be identifiable and traceable.
# Rule 3  Allowed values - course, sibling_enrolled, payment_method and
#         renewal must be values the business rules know.
#         Why: the pricing and discount rules only exist for those values; a
#         typo such as "Italian" or "maybe" would silently give a wrong total.
# Rule 4  Business key - enrollment_id unique across the whole batch.
#         Why: a repeated enrollment would be counted twice in revenue.
# =========================================================

from school_rules import COURSE_PRICES

EXPECTED_COLUMNS = [
    "enrollment_id", "student_name", "course",
    "sibling_enrolled", "payment_method", "renewal", "coupon_code",
]
YES_NO_VALUES = ["yes", "no"]
PAYMENT_VALUES = ["upfront", "monthly"]


def clean_text_columns(data):
    """Cleaning: trim spaces and standardize capitalization."""
    for column in EXPECTED_COLUMNS:
        data[column] = data[column].str.strip()
    data["course"] = data["course"].str.title()
    for column in ("sibling_enrolled", "payment_method", "renewal"):
        data[column] = data[column].str.lower()
    data["coupon_code"] = data["coupon_code"].str.upper()
    return data


def csv_lines(mask):
    """CSV line numbers (header = line 1) of the rows where mask is True."""
    return [int(index) + 2 for index in mask[mask].index]


def check_allowed_values(data, column, allowed, file_name):
    """Rule 3 for one column."""
    invalid = ~data[column].isin(allowed)
    if invalid.any():
        found = sorted(set(data.loc[invalid, column]))
        raise ValueError(
            f"{file_name}: invalid {column} {found} on CSV line(s) "
            f"{csv_lines(invalid)}; allowed values: {list(allowed)}"
        )


def validate_file(data, file_name):
    """Apply rules 1-3 to one file and return the cleaned data."""
    # Rule 1: structure
    if len(data.columns) == 1 and ";" in str(data.columns[0]):
        raise ValueError(
            f"{file_name}: the file looks semicolon-separated; "
            "save it as a comma-separated UTF-8 CSV"
        )
    missing = [column for column in EXPECTED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"{file_name}: missing required column(s): {missing}")
    if list(data.columns) != EXPECTED_COLUMNS:
        raise ValueError(
            f"{file_name}: columns must be exactly {EXPECTED_COLUMNS}, "
            f"found {list(data.columns)}"
        )
    if data.empty:
        raise ValueError(f"{file_name}: the file has no data rows")

    data = clean_text_columns(data)

    # Rule 2: required text
    for column in ("enrollment_id", "student_name"):
        blank = data[column].eq("")
        if blank.any():
            raise ValueError(
                f"{file_name}: blank {column} on CSV line(s) {csv_lines(blank)}"
            )

    # Rule 3: allowed values
    check_allowed_values(data, "course", list(COURSE_PRICES), file_name)
    check_allowed_values(data, "sibling_enrolled", YES_NO_VALUES, file_name)
    check_allowed_values(data, "payment_method", PAYMENT_VALUES, file_name)
    check_allowed_values(data, "renewal", YES_NO_VALUES, file_name)
    return data


def validate_batch(orders):
    """Rule 4: enrollment_id must be unique across all files of the batch."""
    repeated = orders["enrollment_id"].duplicated(keep=False)
    if repeated.any():
        details = []
        for enrollment_id in sorted(orders.loc[repeated, "enrollment_id"].unique()):
            places = orders[orders["enrollment_id"] == enrollment_id]
            where = ", ".join(
                f"{row.source_file} line {row.source_line}"
                for row in places.itertuples()
            )
            details.append(f"{enrollment_id} ({where})")
        raise ValueError("Repeated enrollment_id across the batch: " + "; ".join(details))
