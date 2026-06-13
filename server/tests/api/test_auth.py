from httpx import AsyncClient
from src.models.postgres.users import UserModel


async def test_login_success(client: AsyncClient, test_user: UserModel) -> None:
    response = await client.post("/api/users/login", json={"email": "test@example.com", "password": "testpass123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"


async def test_login_wrong_password(client: AsyncClient, test_user: UserModel) -> None:
    response = await client.post("/api/users/login", json={"email": "test@example.com", "password": "wrongpass"})
    assert response.status_code == 401


async def test_login_nonexistent_user(client: AsyncClient) -> None:
    response = await client.post("/api/users/login", json={"email": "nobody@example.com", "password": "anything"})
    assert response.status_code == 401


async def test_get_me_authenticated(auth_client: AsyncClient, test_user: UserModel) -> None:
    response = await auth_client.get("/api/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["id"] == str(test_user.id)


async def test_get_me_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_get_me_invalid_token(client: AsyncClient) -> None:
    client.headers["Authorization"] = "Bearer invalidtoken"
    response = await client.get("/api/users/me")
    assert response.status_code == 401


async def test_create_anonymous_user(client: AsyncClient) -> None:
    response = await client.post("/api/users/")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] is None
    assert data["user"]["is_verified"] is False


async def test_register_user(client: AsyncClient) -> None:
    # Create anonymous user first
    create_response = await client.post("/api/users/")
    token = create_response.json()["access_token"]

    # Register with email/password
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.post("/api/users/register", json={"email": "new@example.com", "password": "newpass123"})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "new@example.com"
    assert data["user"]["is_verified"] is True
