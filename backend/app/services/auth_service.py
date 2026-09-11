from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import ApiError, email_not_verified
from app.models.auth_session import PasswordResetToken, RefreshSession
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from app.security.passwords import hash_password, verify_password
from app.security.tokens import hash_secret
from app.services.rate_limit import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)

_refresh_locks: dict[str, asyncio.Lock] = {}
_refresh_locks_guard = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invalid_reset() -> ApiError:
    return ApiError(400, "INVALID_RESET_TOKEN", "Lenken er ugyldig eller utløpt.")


def _account_link_required() -> ApiError:
    return ApiError(
        409,
        "ACCOUNT_LINK_REQUIRED",
        "Kontoen kan ikke kobles automatisk. Logg inn med passord.",
    )


def _rate_limited() -> ApiError:
    return ApiError(
        429,
        "RATE_LIMITED",
        "For mange forsøk. Prøv igjen senere.",
        retryable=True,
    )


async def _lock_for(key: str) -> asyncio.Lock:
    async with _refresh_locks_guard:
        lock = _refresh_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _refresh_locks[key] = lock
        return lock


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        rate_limiter: RateLimiter | None = None,
    ):
        self.db = db
        self.rate_limiter = rate_limiter or get_rate_limiter()

    async def _issue_tokens(
        self,
        user_id: uuid.UUID,
        *,
        family_id: uuid.UUID | None = None,
    ) -> TokenResponse:
        session_id = uuid.uuid4()
        family = family_id or uuid.uuid4()
        expires_at = _now() + timedelta(days=settings.refresh_token_expire_days)
        refresh = create_refresh_token(
            str(user_id),
            jti=str(session_id),
            family_id=str(family),
            expires_at=expires_at,
        )
        self.db.add(
            RefreshSession(
                id=session_id,
                user_id=user_id,
                token_hash=hash_secret(refresh),
                family_id=family,
                expires_at=expires_at,
            )
        )
        await self.db.commit()
        return TokenResponse(
            access_token=create_access_token(str(user_id)),
            refresh_token=refresh,
        )

    def _refresh_jwt_for(self, session: RefreshSession) -> str:
        return create_refresh_token(
            str(session.user_id),
            jti=str(session.id),
            family_id=str(session.family_id),
            expires_at=_as_utc(session.expires_at).replace(microsecond=0),
        )

    async def register(self, email: str, password: str) -> tuple[User, TokenResponse]:
        user = User(email=email.lower(), password_hash=hash_password(password))
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc
        await self.db.refresh(user)
        return user, await self._issue_tokens(user.id)

    async def login(self, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self.get_user_by_email(email.lower())
        if not user or not user.password_hash or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        return user, await self._issue_tokens(user.id)

    async def login_or_register_google(
        self,
        google_sub: str,
        email: str,
        *,
        email_verified: bool = False,
    ) -> tuple[User, TokenResponse]:
        """Google-kobling (P0).

        google_sub er identiteten. Lik e-posttekst alene gir aldri eierskap.

        - google_sub matcher → innlogging.
        - e-post er ny og email_verified er sann → ny bruker.
        - e-post er ny og email_verified er usann → 401 EMAIL_NOT_VERIFIED,
          ingen bruker rad.
        - e-post matcher en eksisterende bruker med annen/mangler google_sub →
          409 ACCOUNT_LINK_REQUIRED. Auto-link skjer ikke, heller ikke når
          email_verified er sann og kontoen allerede eier e-posten via passord.
        """
        user = await self.get_user_by_google_sub(google_sub)
        if user:
            return user, await self._issue_tokens(user.id)

        existing = await self.get_user_by_email(email.lower())
        if existing:
            raise _account_link_required()

        if not email_verified:
            raise email_not_verified()

        user = User(email=email.lower(), google_sub=google_sub)
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unable to create Google user",
            ) from exc
        await self.db.refresh(user)
        return user, await self._issue_tokens(user.id)

    async def refresh(self, raw_token: str) -> TokenResponse:
        lock = await _lock_for(f"refresh:{hash_secret(raw_token)}")
        async with lock:
            return await self._refresh_locked(raw_token)

    async def _refresh_locked(self, raw_token: str) -> TokenResponse:
        try:
            payload = decode_token(raw_token)
        except ValueError as exc:
            raise ValueError("Invalid refresh token") from exc
        if payload.get("type") != "refresh" or not isinstance(payload.get("sub"), str):
            raise ValueError("Invalid refresh token")
        jti = payload.get("jti")
        try:
            session_id = uuid.UUID(str(jti))
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid refresh token") from exc

        session = await self._session_by_id(session_id)
        if session is None or session.token_hash != hash_secret(raw_token):
            raise ValueError("Invalid refresh token")
        if session.revoked_at is not None:
            raise ValueError("Invalid refresh token")
        if _as_utc(session.expires_at) <= _now():
            raise ValueError("Invalid refresh token")

        await self._lock_family(session.family_id)
        await self.db.refresh(session)

        if session.replaced_by is not None:
            replacement = await self._session_by_id(session.replaced_by)
            if (
                replacement is not None
                and replacement.replaced_by is None
                and replacement.revoked_at is None
                and _as_utc(replacement.expires_at) > _now()
            ):
                replayed = self._refresh_jwt_for(replacement)
                if hash_secret(replayed) != replacement.token_hash:
                    raise ValueError("Invalid refresh token")
                return TokenResponse(
                    access_token=create_access_token(str(replacement.user_id)),
                    refresh_token=replayed,
                )
            await self._revoke_family(session.family_id)
            await self.db.commit()
            raise ValueError("Invalid refresh token")

        new_tokens = await self._rotate(session)
        return new_tokens

    async def _rotate(self, session: RefreshSession) -> TokenResponse:
        session_id = uuid.uuid4()
        expires_at = _now() + timedelta(days=settings.refresh_token_expire_days)
        refresh = create_refresh_token(
            str(session.user_id),
            jti=str(session_id),
            family_id=str(session.family_id),
            expires_at=expires_at,
        )
        replacement = RefreshSession(
            id=session_id,
            user_id=session.user_id,
            token_hash=hash_secret(refresh),
            family_id=session.family_id,
            expires_at=expires_at,
        )
        self.db.add(replacement)
        session.replaced_by = session_id
        await self.db.commit()
        return TokenResponse(
            access_token=create_access_token(str(session.user_id)),
            refresh_token=refresh,
        )

    async def request_password_reset(self, email: str) -> None:
        normalized = email.lower()
        limit_key = "pwreset:" + hashlib.sha256(normalized.encode()).hexdigest()
        allowed = await self.rate_limiter.allow(
            limit_key,
            limit=settings.password_reset_request_limit,
            window_seconds=settings.password_reset_request_window_seconds,
        )
        if not allowed:
            raise _rate_limited()

        user = await self.get_user_by_email(normalized)
        if user is None:
            logger.info("password reset requested")
            return

        now = _now()
        await self.db.execute(
            sa.update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw = secrets.token_urlsafe(32)
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_secret(raw),
                expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
            )
        )
        await self.db.commit()
        logger.info("password reset requested")

    async def complete_password_reset(self, token: str, new_password: str) -> None:
        record = (
            await self.db.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == hash_secret(token)
                )
            )
        ).scalar_one_or_none()
        now = _now()
        if (
            record is None
            or record.used_at is not None
            or _as_utc(record.expires_at) <= now
        ):
            raise _invalid_reset()

        user = await self.get_user_by_id(str(record.user_id))
        if user is None:
            record.used_at = now
            await self.db.commit()
            raise _invalid_reset()

        record.used_at = now
        user.password_hash = hash_password(new_password)
        await self._revoke_user_sessions(user.id)
        await self.db.commit()

    async def logout(self, user_id: uuid.UUID, raw_token: str) -> None:
        try:
            payload = decode_token(raw_token)
            session_id = uuid.UUID(str(payload.get("jti")))
        except (ValueError, TypeError):
            return
        session = await self._session_by_id(session_id)
        if session is None or session.user_id != user_id:
            return
        if session.token_hash != hash_secret(raw_token):
            return
        session.revoked_at = _now()
        await self.db.commit()

    async def logout_all(self, user_id: uuid.UUID) -> None:
        await self._revoke_user_sessions(user_id)
        await self.db.commit()

    async def _revoke_user_sessions(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            sa.update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=_now())
        )

    async def _revoke_family(self, family_id: uuid.UUID) -> None:
        await self.db.execute(
            sa.update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=_now())
        )

    async def _lock_family(self, family_id: uuid.UUID) -> None:
        if self.db.bind is None or self.db.bind.dialect.name != "postgresql":
            return
        key = hashlib.sha256(str(family_id).encode()).digest()[:8]
        await self.db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(key, "big", signed=True)},
        )

    async def _session_by_id(self, session_id: uuid.UUID) -> RefreshSession | None:
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        try:
            parsed_id = uuid.UUID(user_id)
        except ValueError:
            return None
        result = await self.db.execute(select(User).where(User.id == parsed_id))
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_google_sub(self, google_sub: str) -> User | None:
        result = await self.db.execute(select(User).where(User.google_sub == google_sub))
        return result.scalar_one_or_none()
