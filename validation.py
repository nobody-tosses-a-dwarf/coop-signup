"""
Validation logic for member signup data.
Validates zip/city/state combinations, phone format, email format.
"""

import re
import json
import os
from pathlib import Path

# US zip code to city/state mapping (loaded from bundled data)
# For production, this uses a comprehensive zip code database.
# For now, we validate format and do basic checks.

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    return True, None


def validate_phone(phone):
    digits = re.sub(r'[\s\-\(\)\.\+]', '', phone)
    # Remove leading 1 for US country code
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return False, "Phone number must be 10 digits"
    if not digits.isdigit():
        return False, "Phone number must contain only digits"
    # Format as (XXX) XXX-XXXX for storage
    formatted = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return True, formatted


def validate_zip(zip_code):
    # Accept 5-digit or ZIP+4 format
    pattern = r'^\d{5}(-\d{4})?$'
    if not re.match(pattern, zip_code.strip()):
        return False, "Zip code must be 5 digits (or ZIP+4 format like 12037-1234)"
    return True, zip_code.strip()[:5]  # Store just 5-digit portion


def validate_state(state):
    valid_states = {
        'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
        'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
        'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
        'TX','UT','VT','VA','WA','WV','WI','WY','DC','PR','VI','GU','AS','MP'
    }
    state_upper = state.strip().upper()
    if state_upper not in valid_states:
        return False, "Invalid US state abbreviation"
    return True, state_upper


def validate_name(name, field_label="Name"):
    name = name.strip()
    if len(name) < 2:
        return False, f"{field_label} must be at least 2 characters"
    if len(name) > 100:
        return False, f"{field_label} must be under 100 characters"
    if re.search(r'[<>{}\\]', name):
        return False, f"{field_label} contains invalid characters"
    return True, name


def validate_address(address):
    address = address.strip()
    if len(address) < 5:
        return False, "Street address seems too short"
    if len(address) > 200:
        return False, "Street address must be under 200 characters"
    return True, address


def validate_city(city):
    city = city.strip()
    if len(city) < 2:
        return False, "City name must be at least 2 characters"
    if len(city) > 100:
        return False, "City name must be under 100 characters"
    return True, city


def validate_signup(data):
    """
    Validate all signup fields. Returns (is_valid, cleaned_data_or_errors).
    If valid, returns (True, cleaned_data_dict).
    If invalid, returns (False, {field: error_message}).
    """
    errors = {}
    cleaned = {}

    # Name 1 (required)
    ok, result = validate_name(data.get("name_1", ""), "Primary name")
    if ok:
        cleaned["name_1"] = result
    else:
        errors["name_1"] = result

    # Name 2 (optional)
    name_2 = data.get("name_2", "").strip()
    if name_2:
        ok, result = validate_name(name_2, "Second name")
        if ok:
            cleaned["name_2"] = result
        else:
            errors["name_2"] = result
    else:
        cleaned["name_2"] = ""

    # Address
    ok, result = validate_address(data.get("street_address", ""))
    if ok:
        cleaned["street_address"] = result
    else:
        errors["street_address"] = result

    # City
    ok, result = validate_city(data.get("city", ""))
    if ok:
        cleaned["city"] = result
    else:
        errors["city"] = result

    # State
    ok, result = validate_state(data.get("state", ""))
    if ok:
        cleaned["state"] = result
    else:
        errors["state"] = result

    # Zip
    ok, result = validate_zip(data.get("zip_code", ""))
    if ok:
        cleaned["zip_code"] = result
    else:
        errors["zip_code"] = result

    # Phone
    ok, result = validate_phone(data.get("phone", ""))
    if ok:
        cleaned["phone"] = result
    else:
        errors["phone"] = result

    # Email
    ok, result = validate_email(data.get("email", ""))
    if ok:
        cleaned["email"] = data["email"].strip().lower()
    else:
        errors["email"] = result

    # Membership type (must be valid int)
    try:
        cleaned["membership_type_id"] = int(data.get("membership_type_id", 0))
        if cleaned["membership_type_id"] < 1:
            errors["membership_type_id"] = "Please select a membership type"
    except (ValueError, TypeError):
        errors["membership_type_id"] = "Invalid membership type"

    # Payment plan
    plan = data.get("payment_plan", "")
    if plan not in ("full", "installment", "deferred"):
        errors["payment_plan"] = "Please select a payment plan"
    else:
        cleaned["payment_plan"] = plan

    if errors:
        return False, errors
    return True, cleaned
