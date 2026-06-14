# Deploying dev-feed-agent

Setup, configuration, and operations. For what the product *is*, see the [root README](../README.md).

Single surface: one `docker-compose.yaml`, one `.env`, prefix-less `make` targets.

## Quick start

```bash
make setup     # create .env from .env.example
# edit .env — at minimum set GITHUB_OAUTH_* , OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN/USERNAME
make build     # build images (server, client, MCP gateways)
make up        # start everything
```

App: `http://localhost:5677` · API docs: `http://localhost:5677/api/docs`

Create a GitHub OAuth App (github.com/settings/developers) with callback URL
`${APP_BASE_URL}/api/auth/github/callback` (locally `http://localhost:5677/api/auth/github/callback`).

Telegram is **webhook-only**: `APP_BASE_URL` must be a public HTTPS URL Telegram can reach, and
`TELEGRAM_WEBHOOK_SECRET` must be set — the app registers the webhook on startup.

The agent and Telegram delivery are otherwise **opt-in**: with no `OPENROUTER_API_KEY` the agent is
off; each MCP source is skipped if its URL/token is unset.

## Commands

| Command | What it does |
|---------|--------------|
| `make setup` | Create `.env` from `.env.example` |
| `make build` / `make up` / `make down` | Build / start / stop all services |
| `make logs [svc]` · `make mcp-logs` | Tail logs (all / the MCP gateways) |
| `make shell` · `make db` | Shell in server · psql in postgres |
| `make make-migrations "msg"` · `make migrate` | Create / apply Alembic migration |
| `make test` · `make lint` · `make format` | pytest / ruff+mypy / autofix (local, via `uv`) |

## Configuration

| Variable | Purpose |
|----------|---------|
| `GITHUB_OAUTH_CLIENT_ID` / `_SECRET` | GitHub OAuth app credentials (sign-in) |
| `APP_BASE_URL` | Public URL; builds the OAuth callback, SPA redirect, and Telegram webhook |
| `SECRET_KEY` | JWT signing key (required) |
| `OPENROUTER_API_KEY` | Enables the agent (empty → off) |
| `AGENT_MODEL` / `PROFILE_BUILDER_MODEL` | OpenRouter model slugs |
| `TELEGRAM_BOT_TOKEN` / `_USERNAME` / `_WEBHOOK_SECRET` | Telegram delivery, deep link, webhook auth |
| `HF_TOKEN`, `MCP_*_URL` | MCP feed sources (per-source opt-in) |
| `PERPLEXITY_API_KEY`, `MCP_PERPLEXITY_URL` | Optional web-grounded Perplexity source (opt-in, cost-aware) |
| `HTTP_PORT` | Host port published by nginx (default 5677) — the only port exposed to the host |
| `FEED_SIZE`, `EXPLORE_RATIO`, `POLL_INTERVAL_MINUTES` | Feed tuning |

## Architecture

```
nginx (reverse proxy, the only host-published port, :5677)
├── /                      → client (built Vue SPA, served static)
├── /api/*                 → server (FastAPI)  ── /api/auth/github/*  (OAuth)
├── /grafana/ /prometheus/ → monitoring
└── server ── postgres (async SQLAlchemy; in-network only, no host port)
         ├── agent (pydantic-ai via OpenRouter)
         │     ├── GitHub tools (repos, deps, issue/repo search)
         │     └── MCP toolsets ── HuggingFace (remote HTTP)
         │                      └── mcp-hn / mcp-arxiv / mcp-reddit / mcp-perplexity (gateway containers; Perplexity opt-in)
         ├── APScheduler (hourly feed)   └── aiogram Telegram bot (webhook)
```

| Service | Purpose |
|---------|---------|
| **server** | FastAPI: OAuth, agent runtime, scheduler, Telegram webhook |
| **client** | Vue 3 SPA (landing + Connect + Go-to-Telegram) |
| **postgres** | Users, connections, profiles, agent message history, feed-item ledger |
| **nginx** | Reverse proxy, serves the built SPA; config in `deploy/nginx/nginx.conf` |
| **mcp-hn / mcp-arxiv / mcp-reddit** | `supergateway` wrapping each stdio MCP server as HTTP (image `deploy/mcp/`) |
| **mcp-perplexity** | Optional web-grounded source (`@perplexity-ai/mcp-server` via `supergateway`); opt-in, API-key-gated |
| **prometheus / grafana** | Metrics + dashboards |

### Backend layout (`server/src/`)

- `agent/` — `prompts/` (system prompts), `tools/` (GitHub, memory, feed, `send_message`),
  `channels/` (output channels: the `Channel` port + `TelegramChannel`), `mcp.py` (MCP toolsets),
  `agents.py` (agent factories), `runtime.py` (`build_profile` / `chat` / `curate_feed`). Chat and the
  feed share one agent + persisted message history; the feed is free-form text.
- `services/` — `github_oauth`, `feed` (per-user pass), `scheduler` (cron), `messaging`
  (channel-agnostic command dispatch), `telegram` (inbound webhook handling).
- `models/postgres/`, `repositories/`, `api/endpoints/` — standard repository-pattern layers.

### Deploy layout (`deploy/`)

- `nginx/` — the nginx reverse-proxy config (`nginx.conf`).
- `mcp/` — Dockerfile for the `supergateway` MCP-gateway image (shared by mcp-hn/arxiv/reddit/perplexity).

## Optional Perplexity source

Perplexity adds web-grounded search/news to complement the developer-centric sources —
mainly for explicit "go deeper" chat queries rather than every cron poll. It's **opt-in**
and API-key-gated: leave `PERPLEXITY_API_KEY` / `MCP_PERPLEXITY_URL` unset and the agent
simply skips it. The `mcp-perplexity` gateway sits behind the `perplexity` compose profile,
so a default `make up` never starts it (the upstream server exits when no key is set, which
would otherwise crash-loop). To enable, set `PERPLEXITY_API_KEY`, set
`MCP_PERPLEXITY_URL=http://mcp-perplexity:8000/mcp`, and start the gateway explicitly:

```bash
docker compose --profile perplexity up -d
```

Like every feed source, Perplexity returns external/untrusted content — the same
prompt-injection caveat applies (returned text is data, never instructions).
