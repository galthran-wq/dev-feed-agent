.PHONY: setup build up down ps logs mcp-logs restart db shell make-migrations migrate test lint format superuser user
.SILENT:

-include .env
export
COMPOSE := docker compose -p $(or $(COMPOSE_PROJECT_NAME),dev-feed-agent)
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
$(ARGS):
	@true

setup:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	@echo "Environment ready. Edit .env, then run: make build && make up"

build:
	$(COMPOSE) build $(ARGS)

up:
	$(COMPOSE) up -d $(ARGS)

down:
	$(COMPOSE) down $(ARGS)

ps:
	$(COMPOSE) ps $(ARGS)

logs:
	$(COMPOSE) logs -f $(ARGS)

mcp-logs:
	$(COMPOSE) logs -f mcp-hn mcp-arxiv mcp-reddit

restart:
	$(COMPOSE) restart $(ARGS)

db:
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

shell:
	$(COMPOSE) exec server bash

make-migrations:
	$(COMPOSE) exec server bash -lc "alembic revision --autogenerate -m '$(ARGS)'"

migrate:
	$(COMPOSE) exec server bash -lc "alembic upgrade head"

# Tests + checks run locally (conftest uses in-memory SQLite — no DB needed).
test:
	cd server && uv run pytest tests/ $(ARGS)

lint:
	cd server && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src

format:
	cd server && uv run ruff format src tests && uv run ruff check --fix src tests

superuser:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make superuser <email_or_uuid|--list|--help>"; \
	else \
		$(COMPOSE) exec -w /app server python scripts/make_superuser.py $(ARGS); \
	fi

user:
	@if [ -z "$(word 1,$(ARGS))" ] || [ -z "$(word 2,$(ARGS))" ]; then \
		echo "Usage: make user <email> <password>"; \
	else \
		$(COMPOSE) exec -w /app server python scripts/create_user.py $(ARGS); \
	fi
