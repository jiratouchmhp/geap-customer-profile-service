"""Profile repository.

Backed by the service's own Cloud SQL database (DS-CPS-PROFILE) in
production. An in-memory implementation is used for local runs and tests.
Customer master attributes are owned by the Customer Domain API (SVC-CDA).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

_SEED = {
    "C-1001": {
        "customer_id": "C-1001",
        "full_name": "Tan Mei Ling",
        "email": "meiling.tan@example.com",
        "phone": "+6591234567",
        "address": {
            "line1": "10 ANSON ROAD",
            "line2": "INTERNATIONAL PLAZA",
            "unit_number": "#12-01",
            "city": "SINGAPORE",
            "postcode": "079903",
            "country": "SG",
        },
    },
    "C-1002": {
        "customer_id": "C-1002",
        "full_name": "Somchai Prasert",
        "email": "somchai.p@example.com",
        "phone": "+66812345678",
        "address": {
            "line1": "88 SUKHUMVIT ROAD",
            "line2": None,
            "unit_number": None,
            "city": "BANGKOK",
            "postcode": "10110",
            "country": "TH",
        },
    },
}


class CustomerNotFound(LookupError):
    """Raised when a customer ID does not exist."""


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self._rows = copy.deepcopy(_SEED)

    def get_customer(self, customer_id: str) -> dict | None:
        row = self._rows.get(customer_id)
        return copy.deepcopy(row) if row else None

    def update_customer(self, customer_id: str, changes: dict) -> dict:
        if customer_id not in self._rows:
            raise CustomerNotFound(customer_id)
        self._rows[customer_id].update(changes)
        self._rows[customer_id]["updated_at"] = datetime.now(timezone.utc)
        return copy.deepcopy(self._rows[customer_id])

    def reset(self) -> None:
        self._rows = copy.deepcopy(_SEED)


repository = InMemoryProfileRepository()
