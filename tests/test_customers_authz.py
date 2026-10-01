"""Object-level authorization and validation tests for POST /customer/update (REQ-CPS-007, SEC-AUTHZ-01)."""

from __future__ import annotations

from tests.conftest import auth_header


def test_update_customer_own_profile_allowed(client):
    """TC-CPS-021 / REQ-CPS-007 / SEC-AUTHZ-01: customer can update their own profile."""
    resp = client.post(
        "/customer/update",
        json={"customer_id": "C-1001", "email": "meiling.updated@example.com"},
        headers=auth_header("C-1001"),
    )
    assert resp.status_code == 200
    assert resp.json()["customer"]["email"] == "meiling.updated@example.com"


def test_update_customer_cross_customer_forbidden(client):
    """TC-CPS-022 / REQ-CPS-007 / SEC-AUTHZ-01: cross-customer update is rejected with 403."""
    resp = client.post(
        "/customer/update",
        json={"customer_id": "C-1001", "email": "attacker@example.com"},
        headers=auth_header("C-1002"),
    )
    assert resp.status_code == 403
    assert "not allowed" in resp.json()["detail"]


def test_update_customer_backoffice_scope_allowed(client):
    """TC-CPS-023 / REQ-CPS-007 / SEC-AUTHZ-01: customer:update:any scope permits cross-customer update."""
    resp = client.post(
        "/customer/update",
        json={"customer_id": "C-1001", "phone": "+6599990000"},
        headers=auth_header("C-1002", ["customer:update:any"]),
    )
    assert resp.status_code == 200
    assert resp.json()["customer"]["phone"] == "+6599990000"


def test_update_customer_invalid_postal_code_rejected(client):
    """TC-CPS-024 / REQ-CPS-007 / TST-NEG-03: invalid postal code returns 400."""
    resp = client.post(
        "/customer/update",
        json={
            "customer_id": "C-1001",
            "address": {
                "line1": "10 ANSON ROAD",
                "city": "SINGAPORE",
                "postcode": "BAD",
                "country": "SG",
            },
        },
        headers=auth_header("C-1001"),
    )
    assert resp.status_code == 400
