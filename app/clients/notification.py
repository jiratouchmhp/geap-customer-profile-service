"""Client for notification-service (SVC-NTF).

Sends a profile-changed notification so the customer is informed of changes
to their contact details.
"""

from __future__ import annotations

import httpx

from app.config import settings


def notify_profile_changed(customer_id: str, fields: list[str]) -> bool:
    """Best-effort notification. Returns False on failure."""
    if settings.env == "test":
        return True
    try:
        resp = httpx.post(
            f"{settings.notification_url}/v1/notifications",
            json={"template": "profile_changed", "customer_id": customer_id, "fields": fields},
            timeout=2.0,
        )
        return resp.status_code < 300
    except httpx.HTTPError:
        return False
