"""Build the MCP toolsets the agent talks to.

pydantic-ai opens every toolset together inside ``async with agent``, so one dead endpoint
would abort the whole run. We probe each server first and keep only the ones that answer.
"""

import asyncio

import structlog
from pydantic_ai.mcp import MCPServerStreamableHTTP
from src.core.config import settings

logger = structlog.get_logger()


def build_mcp_servers() -> list[MCPServerStreamableHTTP]:
    servers: list[MCPServerStreamableHTTP] = []

    if settings.hf_mcp_url and settings.hf_token:
        servers.append(
            MCPServerStreamableHTTP(
                url=settings.hf_mcp_url,
                headers={"Authorization": f"Bearer {settings.hf_token}"},
                timeout=settings.mcp_probe_timeout,
            )
        )
    # Gateway containers carry their own auth, so the agent connects with no header.
    for url in (settings.mcp_hn_url, settings.mcp_arxiv_url, settings.mcp_reddit_url):
        if url:
            servers.append(MCPServerStreamableHTTP(url=url, timeout=settings.mcp_probe_timeout))

    # Perplexity is API-key-gated and opt-in (started via the `perplexity` compose profile).
    if settings.perplexity_enabled:
        servers.append(MCPServerStreamableHTTP(url=settings.mcp_perplexity_url, timeout=settings.mcp_probe_timeout))

    logger.info("mcp_servers_configured", count=len(servers))
    return servers


async def _probe_one(server: MCPServerStreamableHTTP, timeout: float) -> bool:
    """True if ``server`` answers within ``timeout``; never raises (unreachable is a soft skip).

    The outer ``asyncio.timeout`` backstops the server's own handshake timeout in case the
    transport hangs before the handshake even starts.
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

    Probes run concurrently, so added latency is ~``mcp_probe_timeout`` worst case, not the sum.

    Caveat: probe-then-use, so a source that passes the probe but dies before the agent
    re-opens it can still abort that run (the alternative, a tolerant toolset wrapper, needs
    upstream support). Each healthy source pays two connect+handshakes per run.
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
