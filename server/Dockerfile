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

# Vendor the tiktoken vocab at build time so token counting never needs network at
# runtime (otherwise the first call fetches it from a remote blob store).
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && chown -R appuser:appuser "$TIKTOKEN_CACHE_DIR"

RUN chmod +x startup.sh

USER appuser
EXPOSE 8000

CMD ["./startup.sh"]
