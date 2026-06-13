FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --chown=appuser:appuser . .

ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x startup.sh

USER appuser
EXPOSE 8000

CMD ["./startup.sh"]
