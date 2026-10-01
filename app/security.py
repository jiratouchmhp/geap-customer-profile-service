"""Authentication helpers for customer-profile-service.

Tokens are compact HMAC-signed JSON documents issued by the enterprise IdP
gateway (simulated here). Production validates against the IdP JWKS.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, status

from app.config import settings


@dataclass
class Principal:
    """Authenticated caller."""

    subject: str
    customer_id: str | None = None
    scopes: list[str] = field(default_factory=list)


class TokenError(Exception):
    """Raised when a bearer token is malformed, forged or expired."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: bytes) -> str:
    digest = hmac.new(settings.jwt_secret.encode(), payload, hashlib.sha256).digest()
    return _b64(digest)


def issue_token(subject: str, customer_id: str | None, scopes: list[str] | None = None) -> str:
    """Issue a token (used by tests and the local dev IdP stub)."""
    body = {
        "sub": subject,
        "cid": customer_id,
        "scp": scopes or [],
        "exp": int(time.time()) + settings.token_ttl_seconds,
    }
    payload = json.dumps(body, separators=(",", ":")).encode()
    return f"{_b64(payload)}.{_sign(payload)}"


def decode_token(token: str) -> dict:
    """Validate signature and expiry and return the claims."""
    try:
        payload_b64, signature = token.split(".", 1)
        payload = _unb64(payload_b64)
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    if not hmac.compare_digest(_sign(payload), signature):
        raise TokenError("bad signature")
    claims = json.loads(payload)
    if claims.get("exp", 0) < time.time():
        raise TokenError("token expired")
    return claims


def get_current_principal(authorization: str | None = Header(default=None)) -> Principal:
    """FastAPI dependency: authenticate the caller (SEC-AUTHN-01)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return Principal(subject=claims["sub"], customer_id=claims.get("cid"), scopes=claims.get("scp", []))


def authorize_customer_access(principal: Principal, customer_id: str, action: str = "write") -> None:
    """Object-level authorization (SEC-AUTHZ-01).

    A caller may act on a customer record only if it is their own record or
    they hold the ``customer:<action>:any`` scope (back-office / agent).
    """
    if principal.customer_id == customer_id:
        return
    if f"customer:{action}:any" in principal.scopes:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed to access this customer")
