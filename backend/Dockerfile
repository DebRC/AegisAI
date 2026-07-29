FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN APP_NAME=AegisAI \
    APP_VERSION=test \
    APP_ENV=test \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_URL=sqlite+pysqlite:///:memory: \
    QDRANT_URL=http://qdrant:6333 \
    JWT_SECRET_KEY=test-only-build-secret \
    JWT_ALGORITHM=HS256 \
    ACCESS_TOKEN_EXPIRE_MINUTES=15 \
    REFRESH_TOKEN_EXPIRE_DAYS=7 \
    python -m unittest discover -s tests -v

RUN APP_NAME=AegisAI \
    APP_VERSION=test \
    APP_ENV=test \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_URL=postgresql://postgres:postgres@postgres:5432/aegis \
    QDRANT_URL=http://qdrant:6333 \
    JWT_SECRET_KEY=test-only-build-secret \
    JWT_ALGORITHM=HS256 \
    ACCESS_TOKEN_EXPIRE_MINUTES=15 \
    REFRESH_TOKEN_EXPIRE_DAYS=7 \
    alembic upgrade head --sql > /tmp/alembic-upgrade.sql

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
