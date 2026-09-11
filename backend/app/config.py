from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRETS = frozenset({"", "change-me-in-production"})
PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("PRISLAPP_ENV", "ENVIRONMENT"),
    )
    database_url: str = "postgresql+asyncpg://prislapp:prislapp@localhost:5432/prislapp"
    database_ssl: bool = False
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    password_reset_expire_minutes: int = 60
    password_reset_request_limit: int = 5
    password_reset_request_window_seconds: int = 3600
    google_client_id: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "receipts"
    minio_secure: bool = False
    redis_url: str = "redis://localhost:6379/0"
    receipt_image_retention_days: int = 30
    celery_task_always_eager: bool = False

    @model_validator(mode="after")
    def reject_insecure_jwt_secret_in_production(self) -> "Settings":
        env = (self.environment or "").strip().lower()
        if env not in PRODUCTION_ENVIRONMENTS:
            return self
        secret = (self.jwt_secret or "").strip()
        if secret in INSECURE_JWT_SECRETS:
            raise ValueError(
                "jwt_secret must be a strong unique value when environment is production"
            )
        return self


settings = Settings()
