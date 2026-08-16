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

**Java / Gradle-krav (lokal maskin):**

- **JDK 25** for å kjøre Gradle (f.eks. Azul Zulu: `brew install --cask zulu@25`, eller tarball under `~/Library/Java/JavaVirtualMachines/`).
- **Gradle 9.5.1** (wrapper) og **AGP 8.13.2** — JDK 25 krever Gradle 9.5+; eldre 8.x feiler ved oppstart med Kotlin DSL på Java 25.
- Sett `JAVA_HOME` til JDK 25, eller `org.gradle.java.home` i `~/.gradle/gradle.properties` / `android/gradle.properties`.
- App-kode kompileres fortsatt mot **Java 17** (`compileOptions` / `jvmTarget`).
- **Java 24:** Gradle 8.14+ løser tidligere «Type T not present» på unit tests; bruk JDK 25 + Gradle 9.5 for anbefalt oppsett.

For Google Sign-In: sett `GOOGLE_WEB_CLIENT_ID` i `android/app/build.gradle.kts` og `GOOGLE_CLIENT_ID` i `backend/.env`.

## Fase 1 status

- [x] Backend skeleton + Docker Compose
- [x] Auth API (register, login, google, me)
- [x] MinIO bucket-oppsett
- [x] Android skeleton + auth UI
- [x] Backend tester (13/13) + Android unit tests
- [x] Fase 2: kamera, opplasting, OCR (se under)

## Fase 2 status

- [x] Backend: receipts/stores/receipt_items modeller + migrasjon
- [x] Backend: POST/GET /receipts, MinIO-opplasting, Celery worker
- [x] Backend: OCR stub + Rema 1000 parser med tester
- [x] Android: CameraX, Room offline-kø, WorkManager-opplasting
- [x] Android: polling UI + gjennomgangsskjerm

## Fase 3 status

- [x] Backend: products/product_aliases/price_observations + migrasjon 003
- [x] Backend: PUT /receipts/{id}/confirm, DELETE /receipts/{id}
- [x] Backend: GET /products/search, GET /products/{id}/my-prices, GET /stores
- [x] Backend: listefilter på GET /receipts (butikk, status)
- [x] Android: redigerbar gjennomgangsskjerm + bekreftelse
- [x] Android: historikk med butikkfilter
- [x] Android: produktsøk og «billigst for meg»
