"""Build the MCP toolsets the agent talks to.

HuggingFace is a remote HTTP MCP; Hacker News / arXiv / Reddit are local gateway
containers (supergateway wraps their stdio servers as streamable HTTP). Each source
is opt-in: a source with no configured URL (or token, for HF) is simply skipped.

A configured source may still be *unreachable* at run time (gateway container down,
HF outage). pydantic-ai opens every toolset together inside ``async with agent``, so a
single dead endpoint would otherwise abort the whole chat/curate run. To stay resilient
we *probe* each server first (open it with a short timeout) and keep only the ones that
answer; dead sources are logged and dropped. The surviving servers are reopened by the
agent for the real run — the MCP connection is reference-counted, so the probe leaves no
state behind.
"""

import asyncio

import structlog
from pydantic_ai.mcp import MCPServerStreamableHTTP
from src.core.config import settings

logger = structlog.get_logger()


def build_mcp_servers() -> list[MCPServerStreamableHTTP]:
    """Instantiate every *configured* MCP server (no network — construction is cheap)."""
    servers: list[MCPServerStreamableHTTP] = []

    if settings.hf_mcp_url and settings.hf_token:
        servers.append(
            MCPServerStreamableHTTP(
                url=settings.hf_mcp_url,
                headers={"Authorization": f"Bearer {settings.hf_token}"},
                timeout=settings.mcp_probe_timeout,
            )
        )
    for url in (settings.mcp_hn_url, settings.mcp_arxiv_url, settings.mcp_reddit_url):
        if url:
            servers.append(MCPServerStreamableHTTP(url=url, timeout=settings.mcp_probe_timeout))

    logger.info("mcp_servers_configured", count=len(servers))
    return servers


async def _probe_one(server: MCPServerStreamableHTTP, timeout: float) -> bool:
    """Open ``server`` (connect + ``initialize`` handshake) and close it again.

    Returns True if it answered within ``timeout`` seconds, False otherwise. Never
    raises — an unreachable source is a soft failure we log and skip. The server's own
    ``timeout`` already bounds the handshake; the outer ``asyncio.timeout`` is a
    belt-and-braces bound in case the transport hangs before the handshake starts.
    """
    try:
        async with asyncio.timeout(timeout):
            async with server:
                pass
        return True
    except Exception as exc:
        logger.warning("mcp_source_unreachable", url=server.url, error=str(exc))
        return False


async def reachable_mcp_servers(
    servers: list[MCPServerStreamableHTTP] | None = None,
) -> list[MCPServerStreamableHTTP]:
    """Return only the configured MCP servers that respond to a probe.

    A dead source is dropped (logged) rather than allowed to abort the whole agent run.
    Probes run concurrently, so added latency is ~``mcp_probe_timeout`` worst case, not
    the sum across sources. An all-unreachable set yields ``[]`` (the agent simply runs
    without MCP tools) instead of raising.

    Caveat: this is a probe-then-use check, so a source that passes the probe but dies in
    the brief window before the agent re-opens it can still abort that run; the window is
    small and the alternative (a tolerant toolset wrapper) needs upstream support. Each
    healthy source also pays two connect+handshakes per run (probe + real open).
    """
    if servers is None:
        servers = build_mcp_servers()
    if not servers:
        return []

    timeout = settings.mcp_probe_timeout
    results = await asyncio.gather(*(_probe_one(s, timeout) for s in servers))
    reachable = [s for s, ok in zip(servers, results, strict=True) if ok]

    dropped = len(servers) - len(reachable)
    if dropped:
        logger.warning("mcp_sources_dropped", dropped=dropped, reachable=len(reachable))
    return reachable
