"""Address validation helpers.

NOTE: copied from shared-validation-lib 1.2 during the 2.3.0 release crunch
(CPS-104). Kept locally so we could ship the normalisation change quickly.
"""

from __future__ import annotations

import re

POSTCODE_PATTERNS = {
    "SG": r"^\d{6}$",
    "TH": r"^\d{5}$",
    "MY": r"^\d{5}$",
    "ID": r"^\d{5}$",
}

MAX_LINE_LENGTH = 80


class AddressValidationError(ValueError):
    """Raised when an address fails validation."""


def normalize_postcode(postcode: str, country: str = "SG") -> str:
    """Strip spaces/dashes and validate the postcode for the country."""
    cleaned = re.sub(r"[\s-]", "", postcode or "")
    pattern = POSTCODE_PATTERNS.get(country.upper())
    if pattern is None:
        raise AddressValidationError(f"unsupported country {country}")
    if not re.match(pattern, cleaned):
        raise AddressValidationError("invalid postcode")
    return cleaned


def normalize_address(address: dict) -> dict:
    """Normalise an address to the enterprise format (REQ-CPS-007).

    Upper-cases and trims text fields and normalises the postcode. The
    unit number is kept in its own field for downstream consumers (billing
    and CRM rely on it - see INC-2041).
    """
    country = (address.get("country") or "SG").upper()
    result = {
        "line1": (address.get("line1") or "").strip().upper(),
        "line2": (address.get("line2") or "").strip().upper() or None,
        "unit_number": (address.get("unit_number") or "").strip() or None,
        "city": (address.get("city") or "").strip().upper(),
        "postcode": normalize_postcode(address.get("postcode", ""), country),
        "country": country,
    }
    return result


def validate_address(address: dict) -> dict:
    """Validate and normalise an address dict. Returns the normalised form."""
    if not address.get("line1"):
        raise AddressValidationError("line1 is required")
    if not address.get("city"):
        raise AddressValidationError("city is required")
    normalized = normalize_address(address)
    for key in ("line1", "line2"):
        value = normalized.get(key)
        if value and len(value) > MAX_LINE_LENGTH:
            raise AddressValidationError(f"{key} too long")
    return normalized
