from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str

    HOST: str
    PORT: int

    DATABASE_URL: str
    QDRANT_URL: str

    DOCUMENT_STORAGE_PATH: str = "/data/documents"
    DOCUMENT_MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    # Bounds parser output independently from the uploaded-byte limit. A small
    # compressed source must not expand without limit inside a worker or DB.
    DOCUMENT_MAX_EXTRACTED_TEXT_CHARACTERS: int = Field(default=5_000_000, ge=1)
    # Character-based defaults keep Phase 8 independent from a future embedding
    # provider. Phase 9 will validate provider-specific token limits.
    DOCUMENT_CHUNK_TARGET_CHARACTERS: int = Field(default=1_200, ge=1)
    DOCUMENT_CHUNK_OVERLAP_CHARACTERS: int = Field(default=200, ge=0)

    # Redis transports Celery messages; PostgreSQL remains authoritative for
    # document-processing jobs and durable outbox events.
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    CELERY_TASK_DEFAULT_QUEUE: str = "aegis-processing"
    CELERY_TASK_TIME_LIMIT_SECONDS: int = 10 * 60
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = 9 * 60
    PROCESSING_OUTBOX_DISPATCH_INTERVAL_SECONDS: int = 30

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    # SSO stays disabled until a deployment explicitly enables it and supplies
    # credentials for at least one provider.
    SSO_ENABLED: bool = False
    SSO_CALLBACK_BASE_URL: str = "http://localhost:8000"
    SSO_STATE_SECRET_KEY: str = ""
    SSO_TRANSACTION_EXPIRE_MINUTES: int = 5

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    MICROSOFT_ENTRA_CLIENT_ID: str = ""
    MICROSOFT_ENTRA_CLIENT_SECRET: str = ""
    MICROSOFT_ENTRA_TENANT_ID: str = "organizations"

    @model_validator(mode="after")
    def validate_chunking_settings(self) -> "Settings":
        """Require overlap to leave each produced chunk with new context."""
        if self.DOCUMENT_CHUNK_OVERLAP_CHARACTERS >= self.DOCUMENT_CHUNK_TARGET_CHARACTERS:
            raise ValueError(
                "DOCUMENT_CHUNK_OVERLAP_CHARACTERS must be smaller than "
                "DOCUMENT_CHUNK_TARGET_CHARACTERS"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()
