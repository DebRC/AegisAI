# AegisAI

AegisAI is a secure, enterprise-grade Retrieval-Augmented Generation (RAG) platform that enables organizations to securely search, retrieve, and interact with internal knowledge using Large Language Models.

> **Current Status:** 🚧 Under Active Development

---

# Features

## Implemented

* FastAPI backend
* PostgreSQL integration
* SQLAlchemy ORM
* Alembic database migrations
* Docker & Docker Compose
* Qdrant Vector Database
* Environment-based configuration
* Health check endpoints
* Database health endpoint
* Authentication database models

## Planned

* JWT Authentication
* Refresh Tokens
* Single Sign-On (Google, GitHub, Microsoft Entra ID)
* Role-Based Access Control (RBAC)
* Document Upload & Ingestion
* Vector Embeddings
* Permission-Aware Retrieval
* RAG Chat
* Audit Logging
* Admin Dashboard
* Multi-Tenant Support
* Kubernetes Deployment

---

# Tech Stack

| Layer            | Technology              |
| ---------------- | ----------------------- |
| Backend          | FastAPI                 |
| ORM              | SQLAlchemy 2.x          |
| Database         | PostgreSQL 16           |
| Vector Database  | Qdrant                  |
| Migrations       | Alembic                 |
| Configuration    | Pydantic Settings       |
| Authentication   | JWT (Upcoming)          |
| Containerization | Docker & Docker Compose |

---

# Project Structure

```text
aegis-ai/
│
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── security/
│   │   ├── services/
│   │   └── main.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── docker-compose.yml
├── README.md
└── .gitignore
```

---

# Prerequisites

Install the following:

* Git
* Docker
* Docker Compose
* Python 3.12+ (optional for local development)

---

# Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/DebRC/aegis-ai.git

cd aegis-ai
```

---

## 2. Create the environment file

```bash
cp backend/.env.example backend/.env
```

Update the values if required.

---

## 3. Build and start the services

```bash
docker compose up --build
```

This starts:

* FastAPI
* PostgreSQL
* Qdrant

---

## 4. Verify the application

### Root Endpoint

```
http://localhost:8000/
```

Expected response:

```json
{
  "service": "AegisAI",
  "version": "0.1.0",
  "environment": "development"
}
```

---

### Health Check

```
GET http://localhost:8000/health
```

---

### Database Health

```
GET http://localhost:8000/database/health
```

---

### Swagger UI

```
http://localhost:8000/docs
```

---

# Database Migrations

Generate a migration after modifying SQLAlchemy models:

```bash
cd backend

alembic revision --autogenerate -m "describe your change"
```

Review the generated migration before applying it.

Apply pending migrations:

```bash
alembic upgrade head
```

View the current migration:

```bash
alembic current
```

View migration history:

```bash
alembic history
```

---

# PostgreSQL Access

Open a shell inside the PostgreSQL container:

```bash
docker exec -it <postgres-container-name> bash
```

Connect using `psql`:

```bash
psql -U postgres -d aegis
```

Useful commands:

```sql
\dt              -- List tables

\d users         -- Describe users table

\d refresh_tokens

SELECT * FROM users;

\q               -- Exit
```

---

# Docker Commands

Start services:

```bash
docker compose up
```

Start in detached mode:

```bash
docker compose up -d
```

Rebuild containers:

```bash
docker compose up --build
```

Stop services:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
```

---

# Current Database Schema

## Users

* id
* email
* full_name
* password_hash
* is_active
* created_at
* updated_at
* last_login

## Refresh Tokens

* id
* token
* expires_at
* user_id
* created_at
* updated_at

---

# Development Workflow

1. Create a feature branch.
2. Modify the SQLAlchemy models.
3. Generate an Alembic migration.
4. Review the generated migration.
5. Apply the migration using `alembic upgrade head`.
6. Verify the application.
7. Commit both the code and the migration.

---

# Roadmap

* [x] Phase 1 — Project Foundation
* [x] Phase 2 — Database Layer
* [x] Phase 3.1 — Authentication Foundation
* [x] Phase 3.2 — Authentication Database Layer
* [ ] Phase 3.3 — Security Layer
* [ ] Phase 3.4 — Authentication Service
* [ ] Phase 3.5 — Authentication API
* [ ] Phase 4 — RBAC
* [ ] Phase 5 — SSO
* [ ] Phase 6 — Document Management
* [ ] Phase 7 — Background Processing
* [ ] Phase 8 — Text Extraction & Chunking
* [ ] Phase 9 — Embeddings & Vector Database
* [ ] Phase 10 — Retrieval Engine
* [ ] Phase 11 — RAG Chat
* [ ] Phase 12 — Permission-Aware Retrieval
* [ ] Phase 13 — Audit Logging
* [ ] Phase 14 — Admin Dashboard
* [ ] Phase 15 — Frontend
* [ ] Phase 16 — Observability
* [ ] Phase 17 — CI/CD
* [ ] Phase 18 — Kubernetes
* [ ] Phase 19 — Multi-Tenancy
* [ ] Phase 20 — Enterprise Features
