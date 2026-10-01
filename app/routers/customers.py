"""Customer profile routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.clients import notification
from app.repository import CustomerNotFound, repository
from app.schemas import Customer, CustomerUpdateRequest
from app.security import Principal, authorize_customer_access, get_current_principal
from app.validators.address import validate_address

router = APIRouter()


@router.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: str, principal: Principal = Depends(get_current_principal)) -> dict:
    """Return a customer profile (REQ-CPS-003)."""
    authorize_customer_access(principal, customer_id, action="read")
    customer = repository.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer not found")
    return customer


@router.post("/customer/update")
def update_customer(req: CustomerUpdateRequest, principal: Principal = Depends(get_current_principal)) -> dict:
    """Update customer contact details (legacy endpoint)."""
    print(f"updating customer {req.customer_id} with {req.model_dump()}")
    changes: dict = {}
    if req.email:
        changes["email"] = req.email
    if req.phone:
        changes["phone"] = req.phone
    if req.address:
        try:
            changes["address"] = validate_address(req.address)
        except Exception:
            raise HTTPException(status_code=400, detail="bad address")
    try:
        customer = repository.update_customer(req.customer_id, changes)
    except CustomerNotFound:
        raise HTTPException(status_code=404, detail="customer not found")
    notification.notify_profile_changed(req.customer_id, list(changes))
    return {"status": "ok", "customer": customer}
