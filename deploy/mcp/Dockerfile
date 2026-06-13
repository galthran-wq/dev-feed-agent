# Shared image for the MCP gateway sidecars.
#
# Each stdio MCP server (Hacker News / arXiv / Reddit) is wrapped by `supergateway`,
# which re-exposes it as a streamable-HTTP MCP endpoint the agent connects to. The
# image carries both node (for `npx` servers + supergateway) and uv (for `uvx arxiv`).
FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

# uv provides `uvx`, used to run the Python arXiv MCP server.
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

# Each compose service overrides `command` with its own supergateway invocation.
EXPOSE 8000
