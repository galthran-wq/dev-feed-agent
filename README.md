# FastAPI + Vue.js Template

Full-stack web application template with FastAPI backend, Vue 3 frontend, PostgreSQL, and Docker Compose orchestration.

## Quick Start

```bash
make setup    # Create .env.dev and .env.prod from examples
make dev-up   # Start all services
```

App: `http://localhost:5746` | API docs: `http://localhost:5746/api/docs`

## Architecture

```
nginx (reverse proxy)
├── /         → client (Vue 3 + Vite)
├── /api/*    → server (FastAPI + uvicorn)
├── /grafana/ → grafana
└── /metrics  → prometheus
    server → postgres (async SQLAlchemy + asyncpg)
```

### Services

| Service | Tech | Purpose |
|---------|------|---------|
| **server** | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic | REST API, JWT auth, business logic |
| **client** | Vue 3.5, TypeScript, Vite, Pinia, Vue Router | SPA frontend |
| **postgres** | PostgreSQL 15 | Primary database |
| **nginx** | Nginx Alpine | Reverse proxy, SSL termination (prod) |
| **prometheus** | Prometheus | Metrics collection |
| **grafana** | Grafana | Metrics dashboards |

## Architectural Decisions

### Single Environment File

All configuration lives in one root-level `.env` file per environment (`.env.dev`, `.env.prod`). No per-service env files. Docker Compose injects variables into containers via `env_file` directives. The server's pydantic-settings config uses `extra="ignore"` to silently discard compose-level variables it doesn't need.

### Explicit Dev/Prod Separation

- `docker-compose.yaml` — base service definitions (shared)
- `docker-compose.dev.yaml` — dev overrides (live reload, exposed ports, dev tools)
- `docker-compose.prod.yaml` — prod overrides (resource limits, restart policies, SSL)

No implicit loading — each environment explicitly composes its files via the Makefile.

### Backend Patterns

- **App factory**: `create_app()` in `src/main.py` for testability
- **Repository pattern**: abstract base in `src/repositories/` — data access decoupled from business logic
- **Async-first**: all database operations use async SQLAlchemy with asyncpg
- **pydantic-settings**: single `Settings` class with env var loading and startup validation
- **JWT auth**: bearer tokens with `get_current_user` / `get_current_superuser` dependency injection
- **Structured logging**: structlog with JSON output in prod, console in dev, request ID tracking
- **Auto-instrumented metrics**: prometheus-fastapi-instrumentator exposes `/metrics`

### Frontend Patterns

- **Composition API only**: `<script setup>` with TypeScript
- **Setup stores**: Pinia stores use `ref()`, `computed()`, and plain functions (not options API)
- **Centralized API client**: axios instance with JWT injection and 401 handling in `src/api/client.ts`
- **Route guards**: `meta.requiresAuth` checked in global `beforeEach`

### Package Management

- **Backend**: uv + pyproject.toml (not pip/requirements.txt)
- **Frontend**: npm

### Code Style

- **Python**: ruff (line-length=120), mypy strict mode, type-annotated
- **TypeScript/Vue**: ESLint + Prettier (no semicolons, single quotes, 100 char width)

## Commands

All commands are in the Makefile. Dev uses `make dev-*`, prod uses `make prod-*`.

```bash
# Setup
make setup                          # Create env files from examples

# Development
make dev-up                         # Start all services
make dev-down                       # Stop services
make dev-logs                       # Tail logs (filter: make dev-logs server)
make dev-build                      # Rebuild images
make dev-shell                      # Bash into server container
make dev-db                         # psql into postgres

# Database
make dev-make-migrations "message"  # Generate Alembic migration
make dev-test-db                    # Create test database (one-time)
make dev-test-migrate               # Run migrations on test DB

# Testing
make dev-test                       # Run all tests
make dev-test -k "test_name"        # Run specific test
cd client && npm run test:unit      # Frontend unit tests

# Code Quality
make dev-lint                       # ruff check + format --check + mypy
make dev-format                     # Auto-fix with ruff

# Production
make prod-up                        # Start prod services
make prod-down                      # Stop prod services
make prod-build                     # Rebuild prod images
```

## Environment Variables

Configuration is split into two files, one per environment:

| Variable | Dev Default | Prod Default | Used By |
|----------|-------------|--------------|---------|
| `PROJECT_NAME` | webapp | webapp | Compose project naming |
| `POSTGRES_USER` | webapp_user | webapp_user | postgres, server |
| `POSTGRES_PASSWORD` | change-me | *(must change)* | postgres, server |
| `POSTGRES_DB` | webapp | webapp | postgres, server |
| `POSTGRES_HOST` | postgres | postgres | server |
| `POSTGRES_PORT` | 5432 | 5432 | server |
| `DEV_POSTGRES_PORT` | 5444 | — | Host port mapping |
| `DEV_NGINX_PORT` | 5746 | — | Host port mapping |
| `PROD_HTTP_PORT` | — | 80 | Host port mapping |
| `PROD_HTTPS_PORT` | — | 443 | Host port mapping |
| `SECRET_KEY` | *(must set)* | *(must set)* | server (JWT signing) |
| `GRAFANA_ADMIN_PASSWORD` | change-me | *(must change)* | grafana |
| `PUBLIC_BASE_URL` | — | https://yourdomain.com | grafana, nginx |

## Project Structure

```
├── server/                 # FastAPI backend
│   ├── src/
│   │   ├── main.py         # App factory
│   │   ├── core/           # Config, database, auth, middleware
│   │   ├── api/            # Route handlers
│   │   ├── models/         # SQLAlchemy models
│   │   └── repositories/   # Data access layer
│   ├── tests/
│   ├── alembic/            # Database migrations
│   └── Dockerfile
├── client/                 # Vue 3 frontend
│   ├── src/
│   │   ├── api/            # API client
│   │   ├── stores/         # Pinia stores
│   │   ├── views/          # Page components
│   │   ├── layouts/        # Layout wrappers
│   │   └── router/         # Vue Router config
│   └── Dockerfile
├── nginx/                  # Nginx configs (dev + prod)
├── monitoring/             # Prometheus + Grafana config
├── docker-compose.yaml     # Base services
├── docker-compose.dev.yaml # Dev overrides
├── docker-compose.prod.yaml # Prod overrides
├── .env.dev.example        # Dev environment template
├── .env.prod.example       # Prod environment template
└── Makefile                # All commands
```
