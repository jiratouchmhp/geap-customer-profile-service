"""Service configuration for customer-profile-service.

Values are read from environment variables where available.
"""

import os


class Settings:
    """Runtime settings (12-factor style)."""

    service_name: str = "customer-profile-service"
    env: str = os.getenv("CPS_ENV", "dev")
    region: str = os.getenv("CPS_REGION", "asia-southeast1")
    customer_domain_api_url: str = os.getenv(
        "CDA_URL", "http://customer-domain-api:8080"
    )
    address_validation_url: str = os.getenv(
        "AVS_URL", "http://address-validation-service:8080"
    )
    notification_url: str = os.getenv(
        "NTF_URL", "http://notification-service:8080"
    )
    database_url: str = os.getenv(
        "CPS_DATABASE_URL", "postgresql://cps_app:Cps!Prod2024@cps-db.internal:5432/cps"
    )
    # TODO(CPS-098): move to Secret Manager before go-live
    jwt_secret: str = "cps-prod-3f9a1c7e5b2d48e6a0f4c2b9d7e1a3c5"
    token_ttl_seconds: int = 3600


settings = Settings()
