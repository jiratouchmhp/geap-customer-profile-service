"""Address validator tests."""

import pytest

from app.validators.address import AddressValidationError, normalize_address, validate_address


def test_validate_address_accepts_valid():
    """TC-CPS-010 / REQ-CPS-006"""
    result = validate_address({"line1": "1 Raffles Place", "city": "Singapore", "postcode": "048616", "country": "SG"})
    assert result["postcode"] == "048616"


def test_validate_address_rejects_bad_postcode():
    """TC-CPS-011 / REQ-CPS-006"""
    with pytest.raises(AddressValidationError):
        validate_address({"line1": "1 Raffles Place", "city": "Singapore", "postcode": "48616", "country": "SG"})


def test_normalize_address_uppercases_and_trims():
    """TC-CPS-012 / REQ-CPS-007 - address normalisation to enterprise format"""
    result = normalize_address({"line1": " 1 raffles place ", "city": "singapore", "postcode": "048 616", "country": "sg"})
    assert result["line1"] == "1 RAFFLES PLACE"
    assert result["city"] == "SINGAPORE"
    assert result["postcode"] == "048616"
    assert result["country"] == "SG"


def test_legacy_address_format_still_accepted():
    """TC-CPS-013 / REQ-CPS-008 - regression for INC-2041 (unit number kept separate)"""
    result = normalize_address(
        {"line1": "10 Anson Road", "unit_number": "#12-01", "city": "Singapore", "postcode": "079903"}
    )
    assert result["unit_number"] == "#12-01"
    assert "#12-01" not in result["line1"]
