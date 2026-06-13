# dev-feed-agent

A personalized, **agentic news feed for developers & ML engineers**. Connect your GitHub and the
agent learns what you build, then watches GitHub, HuggingFace, Hacker News, arXiv and Reddit and
delivers a curated feed — projects, good-first-issues, help-wanted tickets, papers, models and
discussions — straight to Telegram. Chat with it to steer what you see.

Built on a FastAPI + Vue 3 + PostgreSQL stack, orchestrated with Docker Compose.

## How it works

1. **Connect with GitHub** (OAuth) on the landing page — that's the entire web UI.
2. The agent builds a **profile** of your interests by exploring your repos and their dependencies
   (an Explore-style sub-agent). The profile is a sectioned markdown document the agent maintains
   itself — it patches a section whenever it learns something new or you state a preference.
3. **Link Telegram** with one tap. From then on everything happens there.
4. An hourly job **curates a feed** across all sources, balancing *exploitation* (your known
   interests) with *exploration* (adjacent new horizons), de-dups against what you've already seen,
   and delivers the top matches. Chat anytime to dig deeper or change direction.

The LLM judges relevance by reasoning over your profile — **no embeddings**.

## Quick start

```bash
make setup     # create .env from .env.example
# edit .env — at minimum set GITHUB_OAUTH_* , OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN/USERNAME
make build     # build images (server, client, MCP gateways)
make up        # start everything
```

App: `http://localhost:5746` · API docs: `http://localhost:5746/api/docs`

Create a GitHub OAuth App (github.com/settings/developers) with callback URL
`http://localhost:5746/api/auth/github/callback`.

The agent and Telegram delivery are **opt-in**: with no `OPENROUTER_API_KEY` the agent is off; with
no `TELEGRAM_BOT_TOKEN` delivery is off. Each MCP source is skipped if its URL/token is unset.

## Commands

| Command | What it does |
|---------|--------------|
| `make setup` | Create `.env` from `.env.example` |
| `make build` / `make up` / `make down` | Build / start / stop all services |
| `make logs [svc]` · `make mcp-logs` | Tail logs (all / the MCP gateways) |
| `make shell` · `make db` | Shell in server · psql in postgres |
| `make make-migrations "msg"` · `make migrate` | Create / apply Alembic migration |
| `make test` · `make lint` · `make format` | Run pytest / ruff+mypy / autofix (local, via `uv`) |

## Architecture

```
nginx (reverse proxy, :5746)
├── /                      → client (built Vue SPA, served static)
├── /api/*                 → server (FastAPI)  ── /api/auth/github/*  (OAuth)
├── /grafana/ /prometheus/ → monitoring
└── server ── postgres (async SQLAlchemy)
         ├── agent (pydantic-ai via OpenRouter)
         │     ├── GitHub tools (repos, deps, issue/repo search)
         │     └── MCP toolsets ── HuggingFace (remote HTTP)
         │                      └── mcp-hn / mcp-arxiv / mcp-reddit  (gateway containers)
         ├── APScheduler (hourly feed)   └── aiogram Telegram bot
```

| Service | Purpose |
|---------|---------|
| **server** | FastAPI: OAuth, agent runtime, scheduler, Telegram bot |
| **client** | Vue 3 SPA (landing + Connect + Go-to-Telegram) |
| **postgres** | Users, connections, profiles, chat, feed-item ledger |
| **nginx** | Reverse proxy, serves the built SPA |
| **mcp-hn / mcp-arxiv / mcp-reddit** | `supergateway` wrapping each stdio MCP server as HTTP |
| **prometheus / grafana** | Metrics + dashboards |

### Backend layout (`server/src/`)

- `agent/` — the agent layer: `prompts/` (system prompts), `tools/` (GitHub + memory + feed tools),
  `mcp.py` (MCP toolsets), `agents.py` (agent factories + curation schema), `runtime.py`
  (`build_profile` / `chat` / `curate_feed`).
- `services/` — `github_oauth`, `feed` (per-user pass), `scheduler` (cron), `telegram_bot`, `notifier`.
- `models/postgres/`, `repositories/`, `api/endpoints/` — standard repository-pattern layers.

## Configuration

| Variable | Purpose |
|----------|---------|
| `GITHUB_OAUTH_CLIENT_ID` / `_SECRET` | GitHub OAuth app credentials (sign-in) |
| `APP_BASE_URL` | Public URL; builds the OAuth callback + SPA redirect |
| `OPENROUTER_API_KEY` | Enables the agent (empty → off) |
| `AGENT_MODEL` / `PROFILE_BUILDER_MODEL` | OpenRouter model slugs |
| `TELEGRAM_BOT_TOKEN` / `_USERNAME` | Telegram delivery + deep link |
| `HF_TOKEN`, `MCP_*_URL` | MCP feed sources (per-source opt-in) |
| `FEED_SIZE`, `EXPLORE_RATIO`, `RELEVANCE_THRESHOLD`, `POLL_INTERVAL_MINUTES` | Feed tuning |
