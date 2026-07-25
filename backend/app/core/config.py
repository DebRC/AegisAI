import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip()

        if value.startswith(("'", '"')) and value.endswith(value[0]):
            value = value[1:-1]

        values[key.strip()] = value

    return values


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str

    HOST: str
    PORT: int

    DATABASE_URL: str
    QDRANT_URL: str


settings = Settings(**{**load_env_file(ENV_FILE), **os.environ})
