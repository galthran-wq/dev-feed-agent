from httpx import AsyncClient
from src.models.postgres.users import UserModel


async def test_superuser_create_user(superuser_client: AsyncClient) -> None:
    response = await superuser_client.post(
        "/api/users/create-user", json={"email": "created@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["email"] == "created@example.com"


async def test_superuser_create_duplicate_user(superuser_client: AsyncClient, test_user: UserModel) -> None:
    response = await superuser_client.post(
        "/api/users/create-user", json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"].lower()


async def test_superuser_create_user_short_password(superuser_client: AsyncClient) -> None:
    response = await superuser_client.post(
        "/api/users/create-user", json={"email": "short@example.com", "password": "12345"}
    )
    assert response.status_code == 422


async def test_regular_user_cannot_create_user(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/users/create-user", json={"email": "nope@example.com", "password": "password123"}
    )
    assert response.status_code == 403


async def test_superuser_delete_user(superuser_client: AsyncClient, test_user: UserModel) -> None:
    response = await superuser_client.request(
        "DELETE", "/api/users/delete-user", json={"user_identifier": str(test_user.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


async def test_regular_user_cannot_delete_user(auth_client: AsyncClient) -> None:
    response = await auth_client.request(
        "DELETE", "/api/users/delete-user", json={"user_identifier": "someone@example.com"}
    )
    assert response.status_code == 403


async def test_superuser_cannot_delete_self(superuser_client: AsyncClient, superuser: UserModel) -> None:
    response = await superuser_client.request(
        "DELETE", "/api/users/delete-user", json={"user_identifier": str(superuser.id)}
    )
    assert response.status_code == 403
    assert "cannot delete your own" in response.json()["detail"].lower()


async def test_register_short_password(client: AsyncClient) -> None:
    # Create anonymous user to get a token
    create_response = await client.post("/api/users/")
    token = create_response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.post("/api/users/register", json={"email": "new@example.com", "password": "short"})
    assert response.status_code == 422
