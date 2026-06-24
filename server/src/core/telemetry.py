"""Pydantic Logfire tracing — opt-in via LOGFIRE_TOKEN.

No token => no-op: imports, boot, tests and CI never depend on Logfire being
reachable. With a token, instruments the whole agent stack so a feed run shows up
as one trace: the chat/feed agent, every spawned sub-agent, their tool calls, and
the underlying model + HTTP requests (OpenRouter, the MCP gateways, GitHub,
Trendshift). instrument_pydantic_ai patches the Agent class, so sub-agents nest
under their parent automatically.
"""

import structlog
from fastapi import FastAPI
from src.core.config import settings

logger = structlog.get_logger()


def configure_telemetry(app: FastAPI) -> None:
    if not settings.logfire_token:
        logger.info("logfire_disabled")  # no write token => tracing off
        return

    import logfire

    logfire.configure(
        token=settings.logfire_token,
        service_name=settings.app_name,
        environment=settings.logfire_environment,
        console=False,
        advanced=logfire.AdvancedOptions(base_url=settings.logfire_base_url),
    )
    logfire.instrument_pydantic_ai()  # agents + sub-agents + tool calls + model requests
    logfire.instrument_httpx()  # OpenRouter, MCP gateways, GitHub, Trendshift
    logfire.instrument_fastapi(app, capture_headers=False)  # don't capture headers (auth/secrets)
    logger.info("logfire_enabled", environment=settings.logfire_environment, base_url=settings.logfire_base_url)
