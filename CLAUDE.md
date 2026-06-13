# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack web application template: FastAPI backend + Vue 3 frontend, orchestrated with Docker Compose. Includes Nginx reverse proxy, PostgreSQL, Prometheus metrics, and Grafana dashboards.

## Common Commands

All commands are in the Makefile. Development commands use `make dev-*`, production uses `make prod-*`. Extra args can be passed via `$(ARGS)`.

### Setup
```bash
make setup               # Create .env files from examples (first-time setup)
make dev-up              # Start all dev services (detached)
```

### Development
```bash
make dev-up              # Start all dev services (detached)
make dev-down            # Stop dev services
make dev-logs            # Tail logs (add service name to filter: make dev-logs server)
make dev-build           # Rebuild Docker images
make dev-shell           # Open bash shell in server container
make dev-db              # Open psql shell in postgres container
make dev-make-migrations "message"  # Autogenerate Alembic migration
make dev-lint            # Run ruff check + ruff format --check + mypy
make dev-format          # Auto-fix with ruff format + ruff check --fix
```

### Testing
```bash
make dev-test-db         # Create test database (one-time setup)
make dev-test-migrate    # Run Alembic migrations on test DB
make dev-test            # Run pytest (all tests)
make dev-test -k "test_name"  # Run a single test
```

Tests run against a separate `${POSTGRES_DB}_test` database. The test commands set `POSTGRES_DB` to the test DB and execute inside the server container. Tests can also run locally with `uv run pytest` (uses in-memory SQLite via conftest.py).

### Frontend
```bash
cd client && npm run dev          # Vite dev server
cd client && npm run build        # Type-check + production build
cd client && npm run test:unit    # Vitest unit tests
cd client && npm run test:e2e     # Playwright e2e tests (all browsers)
cd client && npm run lint         # ESLint
cd client && npm run format       # Prettier
```

## Architecture

### Services (Docker Compose)

- **postgres** — PostgreSQL 15 (dev port: 5444)
- **server** — FastAPI on uvicorn (internal :8000)
- **client** — Vue 3 + Vite (internal :5173 in dev)
- **nginx** — Reverse proxy (dev port: 5746)
- **prometheus** / **grafana** — Monitoring stack

Dev uses `docker-compose.yaml` + `docker-compose.dev.yaml`. Prod uses `docker-compose.yaml` + `docker-compose.prod.yaml`.

### URL Routing (Nginx)

| Path | Destination |
|------|-------------|
| `/` | Vue frontend |
| `/api/*` | FastAPI backend |
| `/api/docs` | Swagger UI |
| `/health` | Health check |
| `/ready` | Readiness check (verifies DB connection) |
| `/metrics` | Prometheus metrics |
| `/ws` | WebSocket proxy |
| `/grafana/`, `/prometheus/` | Monitoring UIs |

### Backend (`server/`)

- **Python 3.12**, FastAPI, async SQLAlchemy 2.0 + asyncpg, Alembic migrations
- **Package management**: uv + pyproject.toml (not pip/requirements.txt)
- Entry point: `src/main.py` — app factory pattern (`create_app()`)
- Config: `src/core/config.py` — pydantic-settings, `extra="ignore"`, env vars injected via Docker Compose `env_file`, `SECRET_KEY` required (no default), `is_debug` derived from `LOG_LEVEL`
- Database: `src/core/database.py` — async engine with connection pooling, `AsyncSessionLocal`, `get_postgres_session` dependency
- Auth: `src/core/auth.py` — JWT bearer tokens, `get_current_user` / `get_current_superuser` dependencies
- Models: `src/models/postgres/` — SQLAlchemy models; register new models in `__init__.py` for Alembic autogenerate
- API routing: `src/api/router.py` aggregates all endpoint routers; individual endpoints in `src/api/endpoints/`
- Repository pattern: `src/repositories/` — abstract base + concrete implementations
- Logging: structlog (JSON in prod, console in dev), request ID tracking via middleware
- Metrics: prometheus-fastapi-instrumentator (auto-instrumented, exposed at `/metrics`)
- Exceptions: `src/core/exceptions.py` — `AppError(status_code, detail)` for business logic errors
- Middleware: `src/core/middleware.py` — CORS (outermost), then request logging, then request ID (innermost)
- Container startup: `startup.sh` runs `alembic upgrade head` then starts uvicorn

### Frontend (`client/`)

- **Vue 3.5** (Composition API, `<script setup>`), TypeScript, Vite 7, Pinia 3, Vue Router 4
- Path alias: `@` → `./src`
- Pinia stores use **setup store** style (not options API)
- API client: `src/api/client.ts` — axios instance with JWT injection and 401 handling
- Auth: `src/stores/auth.ts` — login/register/logout with localStorage token persistence
- Router guards: `src/router/index.ts` — `meta.requiresAuth` checked in `beforeEach`
- Views: `src/views/` — LoginView, RegisterView, DashboardView
- Layout: `src/layouts/DefaultLayout.vue` — navbar with auth-aware navigation
- Unit tests: Vitest + jsdom (excludes `e2e/` directory)
- E2E tests: Playwright (Chromium, Firefox, WebKit)

### Code Style

- **Python**: ruff (line-length=120, py312), mypy strict mode, async-first, type-annotated, repository pattern
- **TypeScript/Vue**: ESLint + Prettier (`semi: false`, `singleQuote: true`, `printWidth: 100`), 2-space indent, LF line endings

## Environment Setup

1. Run `make setup` (creates `.env.dev` and `.env.prod` from examples)
2. Start dev: `make dev-up`
3. App at `http://localhost:5746`, API docs at `http://localhost:5746/api/docs`

## Key Patterns

- **Adding a new model**: Create in `src/models/postgres/`, import in `src/models/postgres/__init__.py`, then `make dev-make-migrations "description"`
- **Adding an API route**: Create router in `src/api/endpoints/`, include it in `src/api/router.py`
- **Database sessions**: Use `get_postgres_session` as a FastAPI dependency (`Depends(get_postgres_session)`)
- **Auth-protected endpoints**: Use `Depends(get_current_user)` or `Depends(get_current_superuser)`
- **Business errors**: Raise `AppError(status_code=400, detail="message")` — handled globally
- **Logging**: Use `structlog.get_logger()`, not `logging.getLogger()`
- **Frontend API calls**: Add functions in `src/api/`, use the shared axios instance from `src/api/client.ts`
- **Frontend state**: Create Pinia setup stores in `src/stores/`, use `ref()`, `computed()`, and plain functions
