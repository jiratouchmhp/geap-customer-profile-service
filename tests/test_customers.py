"""Customer route tests (partial coverage - see CPS-107)."""

from tests.conftest import auth_header


def test_get_customer_returns_profile(client):
    """TC-CPS-001 / REQ-CPS-003"""
    resp = client.get("/customers/C-1001", headers=auth_header("C-1001"))
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == "C-1001"


def test_get_customer_not_found(client):
    """TC-CPS-002 / REQ-CPS-003"""
    resp = client.get("/customers/C-9999", headers=auth_header(None, ["customer:read:any"]))
    assert resp.status_code == 404


def test_get_customer_requires_auth(client):
    """TC-CPS-003 / REQ-CPS-004"""
    resp = client.get("/customers/C-1001")
    assert resp.status_code == 401


def test_update_customer_email(client):
    """TC-CPS-020 / REQ-CPS-005"""
    resp = client.post(
        "/customer/update",
        json={"customer_id": "C-1001", "email": "new.mail@example.com"},
        headers=auth_header("C-1001"),
    )
    assert resp.status_code == 200
    assert resp.json()["customer"]["email"] == "new.mail@example.com"
