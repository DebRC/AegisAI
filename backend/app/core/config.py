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

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()
