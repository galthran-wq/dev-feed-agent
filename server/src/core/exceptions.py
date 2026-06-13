import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


# --- Domain exceptions (raised by repositories / business logic) ---


class DomainError(Exception):
    """Base class for all domain/business-logic errors."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ConflictError(DomainError):
    """Raised when an operation conflicts with existing state (e.g., duplicate email)."""


class ForbiddenError(DomainError):
    """Raised when an operation is not permitted by business rules."""


# --- Application-level error (explicit HTTP status) ---


class AppError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


# --- Exception handlers ---


async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    logger.warning("validation_error", errors=errors, path=request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.detail})


async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": exc.detail})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, method=request.method, error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, conflict_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ForbiddenError, forbidden_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AppError, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
