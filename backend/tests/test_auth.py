import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    register = await client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "TestPass123!"},
    )
    assert register.status_code == 201
    tokens = register.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    login = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "TestPass123!"},
    )
    assert login.status_code == 200

    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "TestPass123!"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409
