import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.auth import TokenResponse
from app.security.jwt import create_access_token, create_refresh_token
from app.security.passwords import hash_password, verify_password


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _token_response(self, user_id: uuid.UUID) -> TokenResponse:
        user_id_str = str(user_id)
        return TokenResponse(
            access_token=create_access_token(user_id_str),
            refresh_token=create_refresh_token(user_id_str),
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
        return user, self._token_response(user.id)

    async def login(self, email: str, password: str) -> tuple[User, TokenResponse]:
        user = await self.get_user_by_email(email.lower())
        if not user or not user.password_hash or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        return user, self._token_response(user.id)

    async def login_or_register_google(self, google_sub: str, email: str) -> tuple[User, TokenResponse]:
        user = await self.get_user_by_google_sub(google_sub)
        if user:
            return user, self._token_response(user.id)

        existing = await self.get_user_by_email(email.lower())
        if existing:
            existing.google_sub = google_sub
            await self.db.commit()
            await self.db.refresh(existing)
            return existing, self._token_response(existing.id)

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
        return user, self._token_response(user.id)

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
