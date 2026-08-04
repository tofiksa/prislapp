# Fase 1 – Fundament Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Etablere kjørbart fundament for Prislapp – selvhostet FastAPI-backend med auth og database, pluss Android-app med innlogging, Google Sign-In og grunnleggende navigasjon til hjem-skjerm.

**Architecture:** Monorepo med `backend/` (FastAPI + PostgreSQL + MinIO via Docker Compose) og `android/` (Kotlin Compose MVVM). Android kommuniserer med backend over REST + JWT. Fase 1 implementerer kun auth og infrastruktur – ingen kvitteringsopplasting eller OCR ennå.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, MinIO, Redis 7 (container only, brukes i Fase 2), Kotlin, Jetpack Compose, Hilt, Retrofit, DataStore, Navigation Compose, Credential Manager (Google Sign-In).

## Global Constraints

- Android minSdk **26**, targetSdk **35**, locale **nb-NO**
- Backend: **Python FastAPI**, selvhostet via **Docker Compose**
- Auth: **e-post + passord** og **Google Sign-In**
- JWT access token **15 min**, refresh token **7 dager**
- Passord: **bcrypt**
- Prishistorikk er **bruker-scopet** (ingen aggregert data på tvers av brukere)
- Varsling: **polling** (ikke push i MVP)
- Bilde-lagring: slett etter **30 dager** (implementeres i Fase 2)
- OCR + kvitterings-endepunkter: **Fase 2**, ikke denne planen

## Filstruktur etter Fase 1

```
prislapp/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── models/user.py
│   │   ├── schemas/auth.py
│   │   ├── routers/health.py
│   │   ├── routers/auth.py
│   │   ├── services/auth_service.py
│   │   ├── services/google_auth.py
│   │   └── security/jwt.py
│   │   └── security/passwords.py
│   ├── alembic/
│   ├── tests/test_auth.py
│   ├── tests/test_health.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── .env.example
├── android/
│   ├── app/src/main/java/no/prislapp/
│   │   ├── PrislappApplication.kt
│   │   ├── MainActivity.kt
│   │   ├── di/AppModule.kt
│   │   ├── di/NetworkModule.kt
│   │   ├── data/remote/PrislappApi.kt
│   │   ├── data/remote/AuthInterceptor.kt
│   │   ├── data/remote/dto/AuthDtos.kt
│   │   ├── data/local/TokenStore.kt
│   │   ├── data/repository/AuthRepository.kt
│   │   ├── domain/model/User.kt
│   │   ├── ui/navigation/PrislappNavHost.kt
│   │   ├── ui/navigation/Routes.kt
│   │   ├── ui/theme/Theme.kt
│   │   ├── ui/auth/LoginScreen.kt
│   │   ├── ui/auth/RegisterScreen.kt
│   │   ├── ui/auth/AuthViewModel.kt
│   │   └── ui/home/HomeScreen.kt
│   └── app/src/test/.../AuthViewModelTest.kt
├── testdata/receipts/          (eksisterer)
└── docs/superpowers/specs/     (eksisterer)
```

---

## Del A – Backend

### Task 1: Backend-prosjektskeleton og Docker Compose

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/app/routers/health.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `GET /health` → `{"status": "ok", "postgres": "...", "minio": "..."}`

- [ ] **Step 1: Opprett requirements.txt**

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic-settings==2.7.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.20
httpx==0.28.1
google-auth==2.37.0
minio==7.2.12
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Opprett config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://prislapp:prislapp@localhost:5432/prislapp"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    google_client_id: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "receipts"
    minio_secure: bool = False


settings = Settings()
```

- [ ] **Step 3: Opprett main.py og health router**

`backend/app/main.py`:

```python
from fastapi import FastAPI
from app.routers import health

app = FastAPI(title="Prislapp API", version="0.1.0")
app.include_router(health.router)


@app.get("/")
async def root():
    return {"name": "Prislapp API", "version": "0.1.0"}
```

`backend/app/routers/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 4: Opprett docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: prislapp
      POSTGRES_PASSWORD: prislapp
      POSTGRES_DB: prislapp
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U prislapp"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - .:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 5: Opprett Dockerfile og .env.example**

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`backend/.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://prislapp:prislapp@postgres:5432/prislapp
JWT_SECRET=dev-secret-change-in-production
GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=receipts
MINIO_SECURE=false
```

- [ ] **Step 6: Skriv health-test**

`backend/tests/test_health.py`:

```python
from httpx import ASGITransport, AsyncClient
from app.main import app
import pytest


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 7: Kjør test**

Run: `cd backend && pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 8: Verifiser Docker**

Run: `cd backend && cp .env.example .env && docker compose up -d postgres minio redis && docker compose up --build api -d`
Expected: `curl http://localhost:8000/health` → `{"status":"ok"}`

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat(backend): add project skeleton and docker compose"
```

---

### Task 2: Database, User-modell og migrasjon

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_create_users.py`
- Modify: `backend/app/main.py` (lifespan for DB)

**Interfaces:**
- Produces: `users`-tabell med kolonner `id`, `email`, `password_hash`, `google_sub`, `created_at`

- [ ] **Step 1: Opprett database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: Opprett User-modell**

`backend/app/models/user.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: Initialiser Alembic og skriv migrasjon**

Run: `cd backend && alembic init alembic`

Rediger `backend/alembic/env.py` til async-oppsett med `target_metadata = Base.metadata`.

Opprett `backend/alembic/versions/001_create_users.py`:

```python
"""create users table

Revision ID: 001
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("google_sub", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade():
    op.drop_table("users")
```

- [ ] **Step 4: Kjør migrasjon**

Run: `cd backend && docker compose up -d postgres && alembic upgrade head`
Expected: `users`-tabell opprettet uten feil

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/app/models/ backend/alembic/
git commit -m "feat(backend): add user model and alembic migration"
```

---

### Task 3: JWT, passord og auth-tjeneste

**Files:**
- Create: `backend/app/security/passwords.py`
- Create: `backend/app/security/jwt.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/services/auth_service.py`
- Create: `backend/app/services/google_auth.py`
- Create: `backend/app/dependencies.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces: `create_access_token(user_id: str) -> str`
- Produces: `create_refresh_token(user_id: str) -> str`
- Produces: `hash_password(plain: str) -> str`
- Produces: `verify_password(plain: str, hashed: str) -> bool`
- Produces: `AuthService.register(email, password) -> TokenPair`
- Produces: `AuthService.login(email, password) -> TokenPair`
- Produces: `verify_google_id_token(token: str) -> GoogleUserInfo`

- [ ] **Step 1: Skriv failing test for passord**

`backend/tests/test_auth_service.py`:

```python
from app.security.passwords import hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("SikkerPassord123!")
    assert verify_password("SikkerPassord123!", hashed) is True
    assert verify_password("FeilPassord", hashed) is False
```

- [ ] **Step 2: Kjør test – forvent FAIL**

Run: `cd backend && pytest tests/test_auth_service.py::test_hash_and_verify_password -v`
Expected: FAIL – module not found

- [ ] **Step 3: Implementer passwords.py og jwt.py**

`backend/app/security/passwords.py`:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

`backend/app/security/jwt.py`:

```python
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "access"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "refresh"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
```

- [ ] **Step 4: Kjør passord-test – forvent PASS**

Run: `cd backend && pytest tests/test_auth_service.py::test_hash_and_verify_password -v`
Expected: PASS

- [ ] **Step 5: Implementer schemas og auth_service**

`backend/app/schemas/auth.py`:

```python
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str

    model_config = {"from_attributes": True}
```

`backend/app/services/auth_service.py` – implementer `register`, `login`, `get_user_by_id` med SQLAlchemy async queries og `IntegrityError`-håndtering (409 ved duplikat e-post).

`backend/app/services/google_auth.py`:

```python
from google.oauth2 import id_token
from google.auth.transport import requests
from app.config import settings


def verify_google_id_token(token: str) -> dict:
    return id_token.verify_oauth2_token(token, requests.Request(), settings.google_client_id)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/security/ backend/app/schemas/ backend/app/services/ backend/tests/
git commit -m "feat(backend): add jwt, password hashing and auth service"
```

---

### Task 4: Auth API-endepunkter

**Files:**
- Create: `backend/app/routers/auth.py`
- Create: `backend/app/dependencies.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `POST /auth/register`, `POST /auth/login`, `POST /auth/google`, `GET /auth/me`
- Consumes: `AuthService`, `get_current_user` dependency

- [ ] **Step 1: Skriv failing integrasjonstest**

`backend/tests/test_auth.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_register_and_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        register = await client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "TestPass123!",
        })
        assert register.status_code == 201
        tokens = register.json()
        assert "access_token" in tokens

        login = await client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "TestPass123!",
        })
        assert login.status_code == 200

        me = await client.get("/auth/me", headers={
            "Authorization": f"Bearer {login.json()['access_token']}"
        })
        assert me.status_code == 200
        assert me.json()["email"] == "test@example.com"
```

- [ ] **Step 2: Kjør test – forvent FAIL**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: FAIL – 404

- [ ] **Step 3: Implementer dependencies.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.security.jwt import decode_token
from app.services.auth_service import AuthService

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        user = await AuthService(db).get_user_by_id(payload["sub"])
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
```

- [ ] **Step 4: Implementer auth router og registrer i main.py**

`backend/app/routers/auth.py` – endepunkter:

| Metode | Path | Respons |
|--------|------|---------|
| POST | `/auth/register` | 201 + TokenResponse |
| POST | `/auth/login` | 200 + TokenResponse |
| POST | `/auth/google` | 200 + TokenResponse (opprett bruker hvis ny) |
| GET | `/auth/me` | 200 + UserResponse |

- [ ] **Step 5: Kjør auth-tester**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: PASS (krever test-database; bruk `DATABASE_URL` mot lokal postgres eller pytest fixture med transaction rollback)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/app/dependencies.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(backend): add auth API endpoints"
```

---

### Task 5: MinIO bucket-oppsett og utvidet health check

**Files:**
- Create: `backend/app/services/storage_service.py`
- Modify: `backend/app/routers/health.py`
- Modify: `backend/app/main.py` (startup event)
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Produces: `StorageService.ensure_bucket()` – oppretter `receipts`-bucket ved oppstart
- Produces: `GET /health` inkluderer `"minio": "ok"` når bucket er tilgjengelig

- [ ] **Step 1: Implementer StorageService**

```python
from minio import Minio
from app.config import settings


class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(settings.minio_bucket):
            self.client.make_bucket(settings.minio_bucket)
```

- [ ] **Step 2: Kall ensure_bucket ved app-startup og oppdater health**

Legg til FastAPI lifespan i `main.py` som kaller `StorageService().ensure_bucket()`.

Utvid `/health` til å returnere `"postgres": "ok"` (enkel `SELECT 1`) og `"minio": "ok"`.

- [ ] **Step 3: Verifiser manuelt**

Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok","postgres":"ok","minio":"ok"}`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/storage_service.py backend/app/routers/health.py backend/app/main.py
git commit -m "feat(backend): add minio bucket setup and health checks"
```

---

## Del B – Android

### Task 6: Android-prosjektskeleton

**Files:**
- Create: `android/settings.gradle.kts`
- Create: `android/build.gradle.kts`
- Create: `android/gradle/libs.versions.toml`
- Create: `android/app/build.gradle.kts`
- Create: `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/main/java/no/prislapp/PrislappApplication.kt`
- Create: `android/app/src/main/java/no/prislapp/MainActivity.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/theme/Theme.kt`
- Create: `android/app/src/main/res/values/strings.xml`

**Interfaces:**
- Produces: Kjørbar app med Material 3-tema, `minSdk = 26`, `applicationId = "no.prislapp"`

- [ ] **Step 1: Generer prosjekt med Android Studio eller Gradle**

Alternativt: opprett manuelt med disse nøkkelverdiene i `android/app/build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
}

android {
    namespace = "no.prislapp"
    compileSdk = 35
    defaultConfig {
        applicationId = "no.prislapp"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/\"")
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}
```

`libs.versions.toml` – inkluder: compose-bom, hilt 2.52, retrofit 2.11, okhttp 4.12, datastore 1.1, navigation-compose 2.8, lifecycle 2.8, coroutines 1.9.

- [ ] **Step 2: Opprett PrislappApplication og MainActivity**

```kotlin
@HiltAndroidApp
class PrislappApplication : Application()
```

```kotlin
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PrislappTheme {
                PrislappNavHost()
            }
        }
    }
}
```

- [ ] **Step 3: Verifiser at appen bygger**

Run: `cd android && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add android/
git commit -m "feat(android): add project skeleton with compose and hilt"
```

---

### Task 7: Nettverkslag og token-lagring

**Files:**
- Create: `android/app/src/main/java/no/prislapp/data/remote/PrislappApi.kt`
- Create: `android/app/src/main/java/no/prislapp/data/remote/AuthInterceptor.kt`
- Create: `android/app/src/main/java/no/prislapp/data/remote/dto/AuthDtos.kt`
- Create: `android/app/src/main/java/no/prislapp/data/local/TokenStore.kt`
- Create: `android/app/src/main/java/no/prislapp/di/NetworkModule.kt`
- Create: `android/app/src/main/java/no/prislapp/di/AppModule.kt`

**Interfaces:**
- Produces: `PrislappApi.register()`, `.login()`, `.googleAuth()`, `.getMe()`
- Produces: `TokenStore.saveTokens(access, refresh)`, `.getAccessToken()`, `.clear()`
- Consumes: `BuildConfig.API_BASE_URL`

- [ ] **Step 1: Opprett AuthDtos**

```kotlin
data class RegisterRequest(val email: String, val password: String)
data class LoginRequest(val email: String, val password: String)
data class GoogleAuthRequest(val id_token: String)
data class TokenResponse(val access_token: String, val refresh_token: String, val token_type: String)
data class UserResponse(val id: String, val email: String)
```

- [ ] **Step 2: Opprett PrislappApi**

```kotlin
interface PrislappApi {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("auth/google")
    suspend fun googleAuth(@Body body: GoogleAuthRequest): TokenResponse

    @GET("auth/me")
    suspend fun getMe(): UserResponse
}
```

- [ ] **Step 3: Implementer TokenStore med DataStore**

Lagre `access_token` og `refresh_token` i Preferences DataStore. Eksponer som `Flow<String?>` for access token.

- [ ] **Step 4: Implementer AuthInterceptor**

Hent access token fra TokenStore og legg til `Authorization: Bearer ...` header på alle kall unntatt `/auth/register`, `/auth/login`, `/auth/google`.

- [ ] **Step 5: Wire opp NetworkModule med Hilt**

```kotlin
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton
    fun provideOkHttp(tokenStore: TokenStore): OkHttpClient { /* ... */ }

    @Provides @Singleton
    fun provideApi(client: OkHttpClient): PrislappApi { /* Retrofit */ }
}
```

- [ ] **Step 6: Commit**

```bash
git add android/app/src/main/java/no/prislapp/data/ android/app/src/main/java/no/prislapp/di/
git commit -m "feat(android): add retrofit api client and token store"
```

---

### Task 8: AuthRepository og AuthViewModel

**Files:**
- Create: `android/app/src/main/java/no/prislapp/data/repository/AuthRepository.kt`
- Create: `android/app/src/main/java/no/prislapp/domain/model/User.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/auth/AuthViewModel.kt`
- Test: `android/app/src/test/java/no/prislapp/ui/auth/AuthViewModelTest.kt`

**Interfaces:**
- Produces: `AuthRepository.register(email, password): Result<User>`
- Produces: `AuthRepository.login(email, password): Result<User>`
- Produces: `AuthRepository.loginWithGoogle(idToken: String): Result<User>`
- Produces: `AuthRepository.isLoggedIn(): Flow<Boolean>`
- Produces: `AuthViewModel.uiState: StateFlow<AuthUiState>`

- [ ] **Step 1: Skriv failing ViewModel-test**

```kotlin
@Test
fun loginSuccess_updatesUiStateToLoggedIn() = runTest {
    val repo = FakeAuthRepository()
    val viewModel = AuthViewModel(repo)
    viewModel.login("test@example.com", "TestPass123!")
    advanceUntilIdle()
    assertTrue(viewModel.uiState.value.isLoggedIn)
}
```

- [ ] **Step 2: Kjør test – forvent FAIL**

Run: `cd android && ./gradlew test --tests AuthViewModelTest`
Expected: FAIL

- [ ] **Step 3: Implementer AuthRepository**

Ved vellykket login/register: lagre tokens i TokenStore, kall `getMe()`, returner `User`.

- [ ] **Step 4: Implementer AuthViewModel**

```kotlin
data class AuthUiState(
    val isLoading: Boolean = false,
    val isLoggedIn: Boolean = false,
    val error: String? = null,
    val user: User? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    fun login(email: String, password: String) { /* viewModelScope.launch */ }
    fun register(email: String, password: String) { /* ... */ }
    fun loginWithGoogle(idToken: String) { /* ... */ }
}
```

- [ ] **Step 5: Kjør test – forvent PASS**

Run: `cd android && ./gradlew test --tests AuthViewModelTest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add android/app/src/main/java/no/prislapp/data/repository/ android/app/src/main/java/no/prislapp/ui/auth/ android/app/src/test/
git commit -m "feat(android): add auth repository and viewmodel"
```

---

### Task 9: Auth UI og navigasjon

**Files:**
- Create: `android/app/src/main/java/no/prislapp/ui/auth/LoginScreen.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/auth/RegisterScreen.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/home/HomeScreen.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/navigation/Routes.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/navigation/PrislappNavHost.kt`

**Interfaces:**
- Produces: NavGraph med ruter `login`, `register`, `home`
- Produces: Startdestinasjon basert på `authRepository.isLoggedIn()`

- [ ] **Step 1: Opprett Routes**

```kotlin
object Routes {
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val HOME = "home"
}
```

- [ ] **Step 2: Implementer LoginScreen**

Compose-skjerm med:
- E-postfelt (`OutlinedTextField`)
- Passordfelt
- «Logg inn»-knapp → `viewModel.login()`
- «Opprett konto»-lenke → naviger til register
- «Logg inn med Google»-knapp (Task 10)
- Vis `CircularProgressIndicator` ved `isLoading`
- Vis feilmelding ved `error`

- [ ] **Step 3: Implementer RegisterScreen**

Tilsvarende med passord-bekreftelse (client-side validering: min 8 tegn, match).

- [ ] **Step 4: Implementer HomeScreen (placeholder)**

```kotlin
@Composable
fun HomeScreen(onLogout: () -> Unit) {
    Scaffold(
        topBar = { TopAppBar(title = { Text("Prislapp") }) }
    ) { padding ->
        Column(Modifier.padding(padding).padding(16.dp)) {
            Text("Velkommen!")
            Button(onClick = onLogout) { Text("Logg ut") }
            // Placeholder for «Ta bilde» – implementeres i Fase 2
            OutlinedButton(onClick = {}, enabled = false) {
                Text("Ta bilde av kvittering (kommer snart)")
            }
        }
    }
}
```

- [ ] **Step 5: Implementer PrislappNavHost**

```kotlin
@Composable
fun PrislappNavHost(
    authViewModel: AuthViewModel = hiltViewModel(),
) {
    val navController = rememberNavController()
    val uiState by authViewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(uiState.isLoggedIn) {
        if (uiState.isLoggedIn) {
            navController.navigate(Routes.HOME) {
                popUpTo(Routes.LOGIN) { inclusive = true }
            }
        }
    }

    NavHost(navController, startDestination = Routes.LOGIN) {
        composable(Routes.LOGIN) { LoginScreen(/* ... */) }
        composable(Routes.REGISTER) { RegisterScreen(/* ... */) }
        composable(Routes.HOME) { HomeScreen(onLogout = { authViewModel.logout() }) }
    }
}
```

- [ ] **Step 6: Manuell verifikasjon**

1. Start backend: `cd backend && docker compose up`
2. Kjør app på emulator (API → `10.0.2.2:8000`)
3. Registrer bruker → skal navigere til Home
4. Logg ut → tilbake til Login
5. Logg inn → Home

- [ ] **Step 7: Commit**

```bash
git add android/app/src/main/java/no/prislapp/ui/
git commit -m "feat(android): add auth screens and navigation"
```

---

### Task 10: Google Sign-In

**Files:**
- Modify: `android/app/build.gradle.kts` (Credential Manager dependency)
- Modify: `android/app/src/main/AndroidManifest.xml`
- Create: `android/app/src/main/java/no/prislapp/ui/auth/GoogleSignInHelper.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/auth/LoginScreen.kt`
- Modify: `backend/.env.example` (GOOGLE_CLIENT_ID)

**Interfaces:**
- Produces: `GoogleSignInHelper.getIdToken(activity): Result<String>`
- Consumes: `GOOGLE_CLIENT_ID` i backend og Android OAuth-klient

- [ ] **Step 1: Opprett OAuth-klient i Google Cloud Console**

- Android-klient: package `no.prislapp`, SHA-1 fra debug keystore
- Web-klient: brukes som `GOOGLE_CLIENT_ID` i backend

- [ ] **Step 2: Implementer GoogleSignInHelper med Credential Manager**

```kotlin
class GoogleSignInHelper(private val context: Context) {
    suspend fun getIdToken(): Result<String> {
        // Credential Manager GetGoogleIdOption med serverClientId
        // Returner idToken ved suksess
    }
}
```

- [ ] **Step 3: Koble knapp i LoginScreen til viewModel.loginWithGoogle(idToken)**

- [ ] **Step 4: Sett GOOGLE_CLIENT_ID i backend .env og test**

Run: Google Sign-In på emulator → backend `POST /auth/google` → navigering til Home

- [ ] **Step 5: Commit**

```bash
git add android/ backend/.env.example
git commit -m "feat: add google sign-in for android and backend"
```

---

## Verifikasjon – Fase 1 ferdig

Kjør denne sjekklisten før Fase 2 startes:

- [ ] `docker compose up` starter postgres, redis, minio og api uten feil
- [ ] `curl http://localhost:8000/health` returnerer postgres + minio ok
- [ ] `POST /auth/register` og `POST /auth/login` fungerer
- [ ] `GET /auth/me` krever gyldig JWT
- [ ] `./gradlew assembleDebug` bygger Android-app
- [ ] App: registrering, innlogging, Google Sign-In og logout fungerer mot lokal backend
- [ ] MinIO-konsoll (`localhost:9001`) viser `receipts`-bucket

## Hva kommer i Fase 2 (ikke denne planen)

- CameraX kvitteringsfoto
- Room offline-kø + WorkManager-opplasting
- `POST /receipts` multipart-endepunkt
- Celery OCR-worker + Rema 1000-parser
- Gjennomgangs-skjerm

---

## Spec-dekning (self-review)

| Spec-krav | Task |
|-----------|------|
| FastAPI backend | Task 1–5 |
| PostgreSQL | Task 2 |
| MinIO | Task 5 |
| Docker Compose | Task 1 |
| Redis container | Task 1 (klargjort for Fase 2) |
| JWT 15 min / refresh 7 dager | Task 3 |
| E-post + passord auth | Task 4 |
| Google Sign-In | Task 10 |
| Android Compose MVVM Hilt | Task 6–9 |
| minSdk 26 | Task 6 |
| Grunnleggende navigasjon | Task 9 |
| Ingen kvittering/OCR ennå | Bevisst utelatt – Fase 2 |

**Placeholder-scan:** Ingen TBD/TODO i planen.
**Type-konsistens:** TokenResponse, UserResponse og AuthDtos er identiske på tvers av backend schemas og Android DTOs.
