from httpx import ASGITransport, AsyncClient
from src.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from src.main import app


async def test_app_error_handler(client: AsyncClient) -> None:
    @app.get("/test-error")
    async def raise_error() -> None:
        raise AppError(status_code=418, detail="I'm a teapot")

    response = await client.get("/test-error")
    assert response.status_code == 418
    assert response.json() == {"detail": "I'm a teapot"}


async def test_not_found_handler(client: AsyncClient) -> None:
    @app.get("/test-not-found")
    async def raise_not_found() -> None:
        raise NotFoundError("Thing not found")

    response = await client.get("/test-not-found")
    assert response.status_code == 404
    assert response.json() == {"detail": "Thing not found"}


async def test_conflict_handler(client: AsyncClient) -> None:
    @app.get("/test-conflict")
    async def raise_conflict() -> None:
        raise ConflictError("Already exists")

    response = await client.get("/test-conflict")
    assert response.status_code == 409
    assert response.json() == {"detail": "Already exists"}


async def test_forbidden_handler(client: AsyncClient) -> None:
    @app.get("/test-forbidden")
    async def raise_forbidden() -> None:
        raise ForbiddenError("Not allowed")

    response = await client.get("/test-forbidden")
    assert response.status_code == 403
    assert response.json() == {"detail": "Not allowed"}


async def test_unhandled_exception_returns_500() -> None:
    @app.get("/test-unhandled")
    async def raise_unhandled() -> None:
        raise RuntimeError("something broke")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/test-unhandled")
    assert response.status_code == 500
