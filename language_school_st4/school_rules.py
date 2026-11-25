# =========================================================
# school_rules.py - Business rules of Global Languages Academy
# =========================================================
# The five calculation functions below come from the ST2 project
# (language_school.py). Their logic is unchanged.
#
# Adaptations made for ST4 (marked "ST4"):
#   - prices, fee, semester length and coupon code moved to constants
#   - calculate_enrollment_fee() extracted from the ST2 main program
#   - is_recognized_coupon() added so the batch can warn about unknown codes
# =========================================================

# ---------- BUSINESS RULE VALUES ----------
COURSE_PRICES = {            # base monthly tuition in USD
    "English": 450.00,
    "Spanish": 420.00,
    "French": 480.00,
}
ENROLLMENT_FEE = 150.00      # charged once per semester, waived on renewal
SEMESTER_MONTHS = 6
RECOGNIZED_COUPON = "PROMO5"


# ---------- FUNCTIONS REUSED FROM ST2 ----------

def get_course_price(course_name, price_table):
    """Look up a course's base price. Returns None if the course is unknown."""
    return price_table.get(course_name)


def calculate_total_discount(has_sibling, pays_upfront, coupon):
    """Sum the applicable discounts (sibling 10%, upfront 5%, PROMO5 5%)."""
    sibling_discount = 0.10 if has_sibling else 0.0
    upfront_discount = 0.05 if pays_upfront else 0.0
    coupon_discount = 0.05 if coupon.strip().upper() == RECOGNIZED_COUPON else 0.0
    return sibling_discount + upfront_discount + coupon_discount


def classify_discount(discount_percentage):
    """Decision rule: classify the discount level (if / elif / else)."""
    if discount_percentage == 0:
        return "No discount"
    elif discount_percentage <= 0.05:
        return "Low discount"
    elif discount_percentage <= 0.10:
        return "Medium discount"
    else:
        return "High discount"


def calculate_final_tuition(base_tuition, discount_percentage):
    """Apply the discount to the base monthly tuition."""
    return base_tuition - (base_tuition * discount_percentage)


def calculate_semester_total(final_tuition, enrollment_fee, months=SEMESTER_MONTHS):
    """Total semester value = tuition for all months + enrollment fee."""
    return (final_tuition * months) + enrollment_fee


# ---------- ST4 ADDITIONS ----------

def calculate_enrollment_fee(is_renewal):
    """ST4: the fee rule that ST2 wrote inline: waived on renewal."""
    return 0.00 if is_renewal else ENROLLMENT_FEE


def is_recognized_coupon(coupon):
    """ST4: True only for a coupon code the school recognizes."""
    return coupon.strip().upper() == RECOGNIZED_COUPON
