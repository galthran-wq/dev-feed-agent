.PHONY: dev-up dev-down dev-ps dev-logs dev-restart dev-db dev-make-migrations dev-test-db dev-test-migrate dev-test dev-lint dev-format dev-shell setup prod-up prod-down prod-ps prod-logs prod-restart prod-build
.SILENT:

-include .env.dev
export
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
$(ARGS):
	@true

setup:
	@test -f .env.dev || (cp .env.dev.example .env.dev && echo "Created .env.dev from .env.dev.example")
	@test -f .env.prod || (cp .env.prod.example .env.prod && echo "Created .env.prod from .env.prod.example")
	@echo "Environment files ready."

dev-up:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) --env-file .env.dev -f docker-compose.yaml -f docker-compose.dev.yaml up -d $(ARGS)

dev-down:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) down $(ARGS)

dev-ps:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) ps $(ARGS)

dev-logs:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) logs -f $(ARGS)

dev-restart:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) restart $(ARGS)

dev-build:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) build $(ARGS)

dev-db:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

dev-make-migrations:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec server bash -lc "python -m alembic revision --autogenerate -m '$(ARGS)'"

dev-test-db:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec postgres createdb -U $(POSTGRES_USER) $(POSTGRES_DB)_test || true

dev-test-migrate:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec -e POSTGRES_DB=$(POSTGRES_DB)_test -e PYTHONPATH=/app server bash -lc "alembic upgrade head"

dev-test:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec -e POSTGRES_DB=$(POSTGRES_DB)_test -e PYTHONPATH=/app server bash -lc "pytest tests/ -v $(ARGS)"

dev-lint:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec server bash -lc "ruff check src tests && ruff format --check src tests && mypy src"

dev-format:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec server bash -lc "ruff format src tests && ruff check --fix src tests"

dev-shell:
	docker compose -p $(COMPOSE_PROJECT_NAME_DEV) exec server bash

dev-superuser:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make dev-superuser <email_or_uuid|--list|--help>"; \
		echo "Examples:"; \
		echo "  make dev-superuser --list"; \
		echo "  make dev-superuser admin@example.com"; \
		echo "  make dev-superuser --help"; \
	else \
		docker compose -p $(COMPOSE_PROJECT_NAME_DEV) --env-file .env.dev -f docker-compose.yaml -f docker-compose.dev.yaml exec -w /app server python scripts/make_superuser.py $(ARGS); \
	fi

dev-user:
	@if [ -z "$(word 1,$(ARGS))" ] || [ -z "$(word 2,$(ARGS))" ]; then \
		echo "Usage: make dev-user <email> <password>"; \
		echo "Examples:"; \
		echo "  make dev-user user@example.com mypassword"; \
		echo "  make dev-user --help                        # Show help"; \
	else \
		docker compose -p $(COMPOSE_PROJECT_NAME_DEV) --env-file .env.dev -f docker-compose.yaml -f docker-compose.dev.yaml exec -w /app server python scripts/create_user.py $(ARGS); \
	fi

prod-up:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) --env-file .env.prod -f docker-compose.yaml -f docker-compose.prod.yaml up -d $(ARGS)

prod-down:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) down $(ARGS)

prod-ps:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) ps $(ARGS)

prod-logs:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) logs -f $(ARGS)

prod-restart:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) restart $(ARGS)

prod-build:
	docker compose -p $(COMPOSE_PROJECT_NAME_PROD) build $(ARGS)

prod-superuser:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make prod-superuser <email_or_uuid|--list|--help>"; \
		echo "Examples:"; \
		echo "  make prod-superuser --list"; \
		echo "  make prod-superuser admin@example.com"; \
		echo "  make prod-superuser --help"; \
	else \
		docker compose -p $(COMPOSE_PROJECT_NAME_PROD) --env-file .env.prod -f docker-compose.yaml -f docker-compose.prod.yaml exec -w /app server python scripts/make_superuser.py $(ARGS); \
	fi

prod-user:
	@if [ -z "$(word 1,$(ARGS))" ] || [ -z "$(word 2,$(ARGS))" ]; then \
		echo "Usage: make prod-user <email> <password>"; \
		echo "Examples:"; \
		echo "  make prod-user user@example.com mypassword"; \
		echo "  make prod-user --help                        # Show help"; \
	else \
		docker compose -p $(COMPOSE_PROJECT_NAME_PROD) --env-file .env.prod -f docker-compose.yaml -f docker-compose.prod.yaml exec -w /app server python scripts/create_user.py $(ARGS); \
	fi
