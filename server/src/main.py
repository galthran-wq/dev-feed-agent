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
    yield
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
