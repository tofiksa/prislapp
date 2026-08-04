# Prislapp

Mobilapp for å samle priser fra dagligvarebutikker via kvitteringsbilder.

## Prosjektstruktur

- `android/` – Kotlin Compose-app
- `backend/` – FastAPI REST API
- `testdata/receipts/` – anonymiserte testkvitteringer
- `docs/superpowers/` – design og implementasjonsplaner

## Backend (lokal utvikling)

```bash
cd backend
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000  
Swagger: http://localhost:8000/docs  
MinIO-konsoll: http://localhost:9001 (minioadmin / minioadmin)

### Tester

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

## Android

```bash
cd android
./gradlew assembleDebug
./gradlew testDebugUnitTest
```

Emulator bruker `http://10.0.2.2:8000/` som API-base-URL.

**Java-krav:** Gradle må kjøre på Java 21 (Java 24 gir feil ved unit tests). Sett `org.gradle.java.home` lokalt, f.eks. i `~/.gradle/gradle.properties`.

For Google Sign-In: sett `GOOGLE_WEB_CLIENT_ID` i `android/app/build.gradle.kts` og `GOOGLE_CLIENT_ID` i `backend/.env`.

## Fase 1 status

- [x] Backend skeleton + Docker Compose
- [x] Auth API (register, login, google, me)
- [x] MinIO bucket-oppsett
- [x] Android skeleton + auth UI
- [x] Backend tester (10/10) + Android unit tests
- [x] Fase 2: kamera, opplasting, OCR (se under)

## Fase 2 status

- [x] Backend: receipts/stores/receipt_items modeller + migrasjon
- [x] Backend: POST/GET /receipts, MinIO-opplasting, Celery worker
- [x] Backend: OCR stub + Rema 1000 parser med tester
- [x] Android: CameraX, Room offline-kø, WorkManager-opplasting
- [x] Android: polling UI + gjennomgangsskjerm (placeholder)
- [ ] Fase 3: redigering, historikk, «billigst for meg»
