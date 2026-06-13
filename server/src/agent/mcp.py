"""Build the MCP toolsets the agent talks to.

HuggingFace is a remote HTTP MCP; Hacker News / arXiv / Reddit are local gateway
containers (supergateway wraps their stdio servers as streamable HTTP). Each source
is opt-in: a source with no configured URL (or token, for HF) is simply skipped.
"""

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
            )
        )
    for url in (settings.mcp_hn_url, settings.mcp_arxiv_url, settings.mcp_reddit_url):
        if url:
            servers.append(MCPServerStreamableHTTP(url=url))

    logger.info("mcp_servers_configured", count=len(servers))
    return servers
