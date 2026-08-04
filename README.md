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
```

Emulator bruker `http://10.0.2.2:8000/` som API-base-URL.

For Google Sign-In: sett `GOOGLE_WEB_CLIENT_ID` i `android/app/build.gradle.kts` og `GOOGLE_CLIENT_ID` i `backend/.env`.

## Fase 1 status

- [x] Backend skeleton + Docker Compose
- [x] Auth API (register, login, google, me)
- [x] MinIO bucket-oppsett
- [x] Android skeleton + auth UI
- [ ] Fase 2: kamera, opplasting, OCR
