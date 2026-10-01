"""customer-profile-service FastAPI application (SVC-CPS)."""

from fastapi import FastAPI

from app.config import settings
from app.routers import customers

app = FastAPI(title="Customer Profile Service", version="2.3.1")
app.include_router(customers.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": settings.service_name}
