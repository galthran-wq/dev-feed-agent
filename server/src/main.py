import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from src.api.router import router
from src.core.config import settings
from src.core.exceptions import register_exception_handlers
from src.core.middleware import register_middleware


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.is_debug else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = structlog.get_logger()
    logger.info("startup", app_name=settings.app_name)

    from src.services import channels, scheduler

    # Telegram is the only channel — the app is useless without it, so require it FIRST,
    # before starting anything we'd then have to tear down on a failed boot.
    if not settings.telegram_bot_token or not settings.telegram_webhook_secret:
        raise RuntimeError(
            "Telegram is required: set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET "
            "(and a public HTTPS APP_BASE_URL Telegram can reach)."
        )

    if settings.discovery_enabled and settings.agent_enabled:
        scheduler.start_scheduler()
    else:
        logger.info("discovery_disabled", agent_enabled=settings.agent_enabled)

    await channels.setup_webhook()

    yield

    await channels.remove_webhook()
    scheduler.stop_scheduler()
    logger.info("shutdown", app_name=settings.app_name)


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.is_debug,
        lifespan=lifespan,
    )

    register_middleware(application)
    register_exception_handlers(application)
    application.include_router(router)

    if settings.metrics_enabled:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            excluded_handlers=["/health", "/ready", "/metrics"],
        ).instrument(application).expose(application, endpoint="/metrics")

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
