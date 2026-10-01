import os

os.environ.setdefault("CPS_ENV", "test")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository import repository
from app.security import issue_token


@pytest.fixture(autouse=True)
def _reset_repo():
    repository.reset()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def auth_header(customer_id: str | None = "C-1001", scopes: list[str] | None = None) -> dict:
    token = issue_token(subject=f"user-{customer_id}", customer_id=customer_id, scopes=scopes)
    return {"Authorization": f"Bearer {token}"}
