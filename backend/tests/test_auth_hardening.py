"""S09-A: passordreset, refresh-sesjoner, Google-kobling, logout og rategrenser."""

from __future__ import annotations

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

ERROR_KEYS = ("code", "message", "field_errors", "retryable", "request_id")
PASSWORD = "TestPass123!"
NEW_PASSWORD = "NyPassord123!"


async def _register(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = PASSWORD,
) -> dict:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assert_c00_error(response, *, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    for key in ERROR_KEYS:
        assert key in body
    assert body["code"] == code
    assert "stack" not in body["message"].lower()
    dumped = str(body).lower()
    assert "traceback" not in dumped
    return body


@pytest.mark.asyncio
async def test_password_reset_request_is_the_same_for_known_and_unknown_email(
    client: AsyncClient,
):
    await _register(client, "known@example.com")

    known = await client.post(
        "/auth/password-reset/request",
        json={"email": "known@example.com"},
    )
    unknown = await client.post(
        "/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.content == unknown.content


@pytest.mark.asyncio
async def test_password_reset_complete_works_once(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "secrets.token_urlsafe",
        lambda _nbytes=32: "one-time-reset-token",
    )
    await _register(client, "reset@example.com")
    requested = await client.post(
        "/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )
    assert requested.status_code == 202

    first = await client.post(
        "/auth/password-reset/complete",
        json={"token": "one-time-reset-token", "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 204
    assert first.content == b""

    second = await client.post(
        "/auth/password-reset/complete",
        json={"token": "one-time-reset-token", "new_password": "AnnetPass123!"},
    )
    body = _assert_c00_error(second, status_code=400, code="INVALID_RESET_TOKEN")
    assert "one-time-reset-token" not in str(body)

    old = await client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": PASSWORD},
    )
    assert old.status_code == 401
    new = await client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": NEW_PASSWORD},
    )
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_complete_invalidates_refresh_sessions(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "secrets.token_urlsafe",
        lambda _nbytes=32: "reset-revokes-sessions",
    )
    tokens = await _register(client, "sessions@example.com")
    refresh = tokens["refresh_token"]

    still_valid = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert still_valid.status_code == 200
    current_refresh = still_valid.json()["refresh_token"]

    requested = await client.post(
        "/auth/password-reset/request",
        json={"email": "sessions@example.com"},
    )
    assert requested.status_code == 202
    completed = await client.post(
        "/auth/password-reset/complete",
        json={"token": "reset-revokes-sessions", "new_password": NEW_PASSWORD},
    )
    assert completed.status_code == 204

    reused = await client.post(
        "/auth/refresh",
        json={"refresh_token": current_refresh},
    )
    assert reused.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_request_does_not_log_email_or_token(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(
        "secrets.token_urlsafe",
        lambda _nbytes=32: "secret-reset-token",
    )
    await _register(client, "logg@example.com")
    with caplog.at_level(logging.INFO):
        await client.post(
            "/auth/password-reset/request",
            json={"email": "logg@example.com"},
        )
    app_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("app.")
    ).lower()
    assert "logg@example.com" not in app_logs
    assert "secret-reset-token" not in app_logs


@pytest.mark.asyncio
async def test_google_does_not_take_over_a_password_account_by_email(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    await _register(client, "same@example.com")
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _token: {
            "sub": "google-sub-1",
            "email": "same@example.com",
            "email_verified": True,
        },
    )

    response = await client.post("/auth/google", json={"id_token": "fake-google-token"})

    body = _assert_c00_error(response, status_code=409, code="ACCOUNT_LINK_REQUIRED")
    assert "same@example.com" not in str(body)

    login = await client.post(
        "/auth/login",
        json={"email": "same@example.com", "password": PASSWORD},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_google_logs_in_when_google_sub_already_matches(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await _register(client, "linked@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "linked@example.com"))
    ).scalar_one()
    user.google_sub = "google-sub-owned"
    await db_session.commit()

    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _token: {
            "sub": "google-sub-owned",
            "email": "linked@example.com",
            "email_verified": True,
        },
    )

    response = await client.post("/auth/google", json={"id_token": "fake-google-token"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()


@pytest.mark.asyncio
async def test_google_creates_an_account_for_a_new_email(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.routers.auth.verify_google_id_token",
        lambda _token: {
            "sub": "google-sub-new",
            "email": "fresh-google@example.com",
            "email_verified": True,
        },
    )

    response = await client.post("/auth/google", json={"id_token": "fake-google-token"})
    assert response.status_code == 200
    me = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "fresh-google@example.com"


@pytest.mark.asyncio
async def test_refresh_rotates_and_innocent_replay_returns_the_same_token(
    client: AsyncClient,
):
    tokens = await _register(client, "rotate@example.com")
    first_refresh = tokens["refresh_token"]

    rotated = await client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotated.status_code == 200
    body = rotated.json()
    assert body["refresh_token"] != first_refresh
    assert "access_token" in body

    replay = await client.post(
        "/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert replay.status_code == 200
    assert replay.json()["refresh_token"] == body["refresh_token"]

    follow = await client.post(
        "/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert follow.status_code == 200


@pytest.mark.asyncio
async def test_replay_of_an_already_rotated_refresh_after_next_use_revokes_the_family(
    client: AsyncClient,
):
    tokens = await _register(client, "reuse@example.com")
    first_refresh = tokens["refresh_token"]

    second = await client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert second.status_code == 200
    second_refresh = second.json()["refresh_token"]

    third = await client.post("/auth/refresh", json={"refresh_token": second_refresh})
    assert third.status_code == 200
    third_refresh = third.json()["refresh_token"]

    replay = await client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401

    current = await client.post("/auth/refresh", json={"refresh_token": third_refresh})
    assert current.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_refresh_replay_does_not_logout_the_user(client: AsyncClient):
    import asyncio

    tokens = await _register(client, "race@example.com")
    refresh = tokens["refresh_token"]

    first, second = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": refresh}),
        client.post("/auth/refresh", json={"refresh_token": refresh}),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["refresh_token"] != refresh
    assert first.json()["refresh_token"] == second.json()["refresh_token"]

    follow = await client.post(
        "/auth/refresh",
        json={"refresh_token": first.json()["refresh_token"]},
    )
    assert follow.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_the_current_refresh(client: AsyncClient):
    tokens = await _register(client, "logout@example.com")
    other = await client.post(
        "/auth/login",
        json={"email": "logout@example.com", "password": PASSWORD},
    )
    assert other.status_code == 200

    logout = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout.status_code == 204

    revoked = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert revoked.status_code == 401

    still_ok = await client.post(
        "/auth/refresh",
        json={"refresh_token": other.json()["refresh_token"]},
    )
    assert still_ok.status_code == 200


@pytest.mark.asyncio
async def test_logout_all_revokes_every_refresh(client: AsyncClient):
    first = await _register(client, "alle@example.com")
    second = await client.post(
        "/auth/login",
        json={"email": "alle@example.com", "password": PASSWORD},
    )
    assert second.status_code == 200

    logout_all = await client.post(
        "/auth/logout-all",
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert logout_all.status_code == 204

    for refresh in (first["refresh_token"], second.json()["refresh_token"]):
        response = await client.post("/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_request_is_rate_limited(client: AsyncClient):
    email = f"limit-{uuid.uuid4().hex}@example.com"
    last = None
    for _ in range(6):
        last = await client.post("/auth/password-reset/request", json={"email": email})
    body = _assert_c00_error(last, status_code=429, code="RATE_LIMITED")
    assert body["retryable"] is True
    assert email.lower() not in str(body).lower()
