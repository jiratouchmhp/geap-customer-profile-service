"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Address(BaseModel):
    line1: str = Field(..., min_length=1, max_length=80)
    line2: str | None = Field(default=None, max_length=80)
    unit_number: str | None = Field(default=None, max_length=16)
    city: str = Field(..., min_length=1, max_length=64)
    postcode: str = Field(..., min_length=4, max_length=10)
    country: str = Field(default="SG", min_length=2, max_length=2)


class Customer(BaseModel):
    customer_id: str
    full_name: str
    email: str
    phone: str | None = None
    address: Address | None = None
    updated_at: datetime | None = None


class CustomerUpdateRequest(BaseModel):
    """Legacy update payload used by POST /customer/update."""

    customer_id: str
    email: str | None = None
    phone: str | None = None
    address: dict | None = None
