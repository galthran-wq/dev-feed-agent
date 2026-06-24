# Shared image for the MCP gateway sidecars.
#
# Each stdio MCP server (Hacker News / arXiv / Reddit) is wrapped by `supergateway`,
# which re-exposes it as a streamable-HTTP MCP endpoint the agent connects to. The
# image carries both node (for `npx` servers + supergateway) and uv (for `uvx arxiv`).
FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

# uv + uvx (separate binaries) — uvx runs the Python arXiv MCP server.
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /usr/local/bin/

# Bake the arXiv MCP server into the image. supergateway spawns its stdio command per
# request; with bare `uvx arxiv-mcp-server` that first spawn re-downloads ~15MB of deps
# and blows past the agent's MCP connect timeout, so the source gets dropped from the
# feed. Pre-installing it (run the `arxiv-mcp-server` binary directly, not via uvx) makes
# every spawn warm. HN/Reddit stay on npx — they're light enough to cold-start in time.
ENV UV_TOOL_BIN_DIR=/usr/local/bin
RUN uv tool install arxiv-mcp-server

# Each compose service overrides `command` with its own supergateway invocation.
EXPOSE 8000
