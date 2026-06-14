# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dev-feed-agent** — a personalized, agentic news feed for developers / ML engineers. Users sign in with GitHub (OAuth); an agent (pydantic-ai over OpenRouter) profiles their interests from their GitHub activity, then curates a feed across GitHub, HuggingFace, Hacker News, arXiv and Reddit (the latter four via MCP) and delivers it to Telegram. Built on a FastAPI + Vue 3 + PostgreSQL template with Nginx.

## Common Commands

A **single build-based surface** — one `docker-compose.yaml`, one `.env`, prefix-less `make` targets. Extra args via `$(ARGS)`.

### Setup & run
```bash
make setup               # Create .env from .env.example (first-time setup)
make build               # Build images (server, client, MCP gateways)
make up                  # Start all services (detached)
make down                # Stop services
make logs [service]      # Tail logs (optionally one service)
make mcp-logs            # Tail the MCP gateway containers
make shell               # bash in the server container
make db                  # psql in the postgres container
make make-migrations "message"  # Autogenerate an Alembic migration (in container)
make migrate             # alembic upgrade head (in container)
```

### Testing & checks (run locally via uv — conftest uses in-memory SQLite, no DB)
```bash
make test                # pytest (all tests)
make test -k "test_name" # single test
make lint                # ruff check + ruff format --check + mypy --strict
make format              # ruff format + ruff check --fix
```

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

- **postgres** — PostgreSQL 15 (in-network only; no host port)
- **server** — FastAPI on uvicorn (internal :8000); also runs the APScheduler feed job + Telegram bot
- **client** — Vue 3; built to static and served by nginx (build-based, no dev server)
- **nginx** — Reverse proxy + static SPA host; the only port published to the host (`HTTP_PORT`, default 5677)
- **mcp-hn / mcp-arxiv / mcp-reddit** — `supergateway` wrapping each stdio MCP server as streamable HTTP (internal :8000, image `deploy/mcp/Dockerfile`)

Single surface: one `docker-compose.yaml`. The client image copies its build into a shared volume that nginx serves; the SPA falls back to `index.html` for deep links (e.g. `/auth/callback`).

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

### Backend (`server/`)

- **Python 3.12**, FastAPI, async SQLAlchemy 2.0 + asyncpg, Alembic migrations
- **Package management**: uv + pyproject.toml (not pip/requirements.txt)
- Entry point: `src/main.py` — app factory pattern (`create_app()`)
- Config: `src/core/config.py` — pydantic-settings, `extra="ignore"`, env vars injected via Docker Compose `env_file`, `SECRET_KEY` required (no default); `LOG_LEVEL` controls log verbosity
- Database: `src/core/database.py` — async engine with connection pooling, `AsyncSessionLocal`, `get_postgres_session` dependency
- Auth: `src/core/auth.py` — JWT bearer tokens, `get_current_user` / `get_current_superuser` dependencies
- Models: `src/models/postgres/` — SQLAlchemy models; register new models in `__init__.py` for Alembic autogenerate
- API routing: `src/api/router.py` aggregates all endpoint routers; individual endpoints in `src/api/endpoints/`
- Repository pattern: `src/repositories/` — abstract base + concrete implementations
- Logging: structlog (JSON, always), request ID tracking via middleware
- Metrics: prometheus-fastapi-instrumentator (auto-instrumented, exposed at `/metrics`)
- Exceptions: `src/core/exceptions.py` — `AppError(status_code, detail)` for business logic errors
- Middleware: `src/core/middleware.py` — CORS (outermost), then request logging, then request ID (innermost)
- Container startup: `startup.sh` runs `alembic upgrade head` then starts uvicorn
- Auth: GitHub OAuth is the primary sign-in (`src/services/github_oauth.py` + `src/api/endpoints/auth_github.py`); it mints the same JWT as the email/password flow. The GitHub access token is stored on `UserModel`.

### Agent (`server/src/agent/`)

- **pydantic-ai** agents over **OpenRouter** (OpenAI-compatible). No embeddings — relevance is judged by the LLM over the profile.
- `prompts/` — system prompts as markdown files (`profile_builder.md`, `chat.md`).
- `tools/` — pydantic-ai tool functions: `github_tools` (repos/starred/dependency scan), `feed_tools` (issue/repo search), `memory_tools` (read/patch profile, list already-shown, `record_feed_items`), `messaging_tools` (`send_message`).
- **Output model**: agents talk to the user **only** via the `send_message` tool, which writes to `deps.channel`. Channels live in the `src/agent/channels/` package: `base.py` has the `Channel` Protocol + `CollectingChannel`; `telegram.py` has the `TelegramChannel` adapter + the shared bot/webhook lifecycle. Runs don't return a reply string — chat, the scheduled feed, and the profile build all deliver by calling `send_message`.
- `mcp.py` — builds MCP toolsets (HuggingFace remote HTTP + the gateway containers); each source is opt-in by config.
- `agents.py` — per-run agent factories (`make_profile_agent`, `make_chat_agent`). One `make_chat_agent` serves **both** Telegram chat and the scheduled feed. A fresh `Agent` per run; MCP connections open inside `async with agent`.
- `runtime.py` — `build_profile` (explore sub-agent; ends by messaging the user the profile is ready), `chat`, and `curate_feed` (a synthetic "assemble the feed" turn). All take a `channel`; chat and feed share one persisted message history. The feed is **free-form text** the agent delivers via `send_message`; it records what it surfaces via `record_feed_items`. `build_profile_safe` runs in the background on first connect / `/init`.
- Memory: the **profile** is a sectioned markdown doc the agent self-edits via `update_profile_section`; `agent_messages` stores the structured pydantic-ai message history (tool calls/results included), replayed via `message_history=` and bounded by a **token budget** (`AGENT_HISTORY_TOKEN_BUDGET`, counted with tiktoken; `/compact` summarizes, `/reset` clears); `feed_items` is the dedup ledger of what's been shown.

### Services (`server/src/services/`)

- `messaging.py` — `process_incoming(channel, session, user, text)`: the single, channel-agnostic entry point for an inbound message (command dispatch `/init`·`/reset`·`/compact` + free text → chat agent). The **caller** resolves the user and owns the session; both `services/telegram.py` (Telegram) and `POST /api/agent/message` (HTTP) funnel through here.
- `telegram.py` — Telegram **inbound**: `handle_update`/`_handle_start` (link via `/start`, resolve chat→user in one session, delegate to `process_incoming`). The webhook endpoint fast-acks and schedules this via `asyncio.create_task`. (Outbound delivery is a *channel*, in `agent/channels/telegram.py`.)
- `feed.py` — one per-user pass: `curate_feed(channel)` (the agent delivers via `send_message`) → mark fed (error-contained).
- `scheduler.py` — APScheduler hourly job over all feedable connections; builds a `TelegramChannel` per user; fresh session per user, never raises.
- (Telegram **outbound** delivery — the shared aiogram `Bot` via `get_bot`, message chunking, the `TelegramChannel` adapter, and webhook registration `setup_webhook`/`remove_webhook` called from the lifespan — is a *channel* and lives in `src/agent/channels/telegram.py`, not here.) There is **no** `telegram_bot.py` and no polling.
- **Telegram is webhook-only** and **required**: `POST /api/telegram/webhook` (`src/api/endpoints/telegram.py`) is pure transport — verifies the secret, dedups `update_id` (`processed_updates`), fast-acks 200, then schedules `services/telegram.py: handle_update` → `process_incoming` (`/start <code>` links the chat). The app raises at startup without `TELEGRAM_BOT_TOKEN` + `TELEGRAM_WEBHOOK_SECRET` (and a public HTTPS `APP_BASE_URL`).

### Frontend (`client/`)

- **Vue 3.5** (Composition API, `<script setup>`), TypeScript, Vite 7, Pinia 3, Vue Router 4
- Path alias: `@` → `./src`
- Pinia stores use **setup store** style (not options API)
- API client: `src/api/client.ts` — axios instance with JWT injection and 401 handling
- Auth: `src/stores/auth.ts` — `setToken` (adopts the OAuth JWT from the callback) + `fetchUser`/`logout`; email/password `login`/`register` kept as a fallback
- Router guards: `src/router/index.ts` — `meta.requiresAuth` checked in `beforeEach`
- Views (minimal): `LandingView` (Connect with GitHub), `AuthCallbackView` (`/auth/callback`), `ConnectedView` (status + Go-to-Telegram). All real interaction happens in Telegram. Login/Register/Dashboard views are kept but unlinked from nav.
- API: `src/api/agent.ts` — `getStatus`, `getTelegramLink`
- Layout: `src/layouts/DefaultLayout.vue` — minimal navbar (brand + Logout)
- Unit tests: Vitest + jsdom (excludes `e2e/` directory)
- E2E tests: Playwright (Chromium, Firefox, WebKit)

### Code Style

- **Python**: ruff (line-length=120, py312), mypy strict mode, async-first, type-annotated, repository pattern
- **TypeScript/Vue**: ESLint + Prettier (`semi: false`, `singleQuote: true`, `printWidth: 100`), 2-space indent, LF line endings

## Environment Setup

1. Run `make setup` (creates `.env` from `.env.example`)
2. Fill `.env`: `GITHUB_OAUTH_CLIENT_ID/_SECRET` (callback `${APP_BASE_URL}/api/auth/github/callback`), `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN/_USERNAME` + `TELEGRAM_WEBHOOK_SECRET` (Telegram is webhook-only and required; `APP_BASE_URL` must be a public HTTPS URL Telegram can reach), optionally `HF_TOKEN`
3. `make build && make up`
4. App at `http://localhost:5677`, API docs at `http://localhost:5677/api/docs`

The agent (OpenRouter), Telegram delivery, and each MCP source are all **opt-in** — absent keys/URLs disable that piece cleanly.

## Key Patterns

- **Adding a new model**: Create in `src/models/postgres/`, import in `src/models/postgres/__init__.py` (also makes it visible to the SQLite test schema), then `make make-migrations "description"`
- **Adding an agent tool**: write an async `fn(ctx: RunContext[AgentDeps], ...) -> str` in `src/agent/tools/`, add it to the relevant list (`GITHUB_TOOLS`/`FEED_TOOLS`/`MEMORY_TOOLS`); tool deps (DB session, GitHub token) come from `ctx.deps`
- **Adding an MCP feed source**: add a config URL + a clause in `src/agent/mcp.py`; add the gateway service in `docker-compose.yaml` if it's a stdio server
- **Adding an API route**: Create router in `src/api/endpoints/`, include it in `src/api/router.py`
- **Database sessions**: Use `get_postgres_session` as a FastAPI dependency (`Depends(get_postgres_session)`)
- **Auth-protected endpoints**: Use `Depends(get_current_user)` or `Depends(get_current_superuser)`
- **Business errors**: Raise `AppError(status_code=400, detail="message")` — handled globally
- **Logging**: Use `structlog.get_logger()`, not `logging.getLogger()`
- **Frontend API calls**: Add functions in `src/api/`, use the shared axios instance from `src/api/client.ts`
- **Frontend state**: Create Pinia setup stores in `src/stores/`, use `ref()`, `computed()`, and plain functions
