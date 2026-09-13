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

Disse testene kjører mot `sqlite+aiosqlite:///:memory:`. SQLite er **ikke** bevis for
Decimal-presisjon i SQL, radlåser eller migrering; det må kjøres mot PostgreSQL.

### PostgreSQL-migreringstester

Testene i `backend/tests/postgres/` (markør `postgres`) krever en disponibel
PostgreSQL 16 og hoppes over uten `PRISLAPP_POSTGRES_TEST_URL`. Hver test oppretter og
sletter en egen database, så brukeren må ha `CREATEDB` og URL-en må peke på en
kastbar instans – aldri produksjon.

```bash
cd backend
docker compose up -d postgres
PRISLAPP_POSTGRES_TEST_URL=postgresql+asyncpg://prislapp:prislapp@localhost:5432/prislapp \
  .venv/bin/python -m pytest -m postgres -q
```

Eget testoppsett uten Compose-volumet:

```bash
docker run --rm -d --name prislapp-pg-test \
  -e POSTGRES_USER=prislapp -e POSTGRES_PASSWORD=prislapp -e POSTGRES_DB=prislapp_test \
  -p 55432:5432 postgres:16-alpine
PRISLAPP_POSTGRES_TEST_URL=postgresql+asyncpg://prislapp:prislapp@localhost:55432/prislapp_test \
  .venv/bin/python -m pytest -m postgres -q
docker rm -f prislapp-pg-test
```

Testene dekker frisk database til head, oppgradering fra stampet 001/002/003/004 uten
tap av `users`/`receipts`, at et `create_all()`-skjema ikke blir feilstampet, og at to
samtidige `run_migrations`-kall serialiseres av migreringslåsen.

## Android

```bash
cd android
./gradlew assembleDebug
./gradlew testDebugUnitTest
```

Standardbygget bruker `https://prislapp-api.sliplane.app/`. For lokal emulator,
sett `api.base.url=http://10.0.2.2:8000/` i `android/local.properties`, eller bygg med
`./gradlew assembleDebug -PapiBaseUrl=http://10.0.2.2:8000/`.

**Java / Gradle-krav (lokal maskin):**

- **JDK 25** for å kjøre Gradle (f.eks. Azul Zulu: `brew install --cask zulu@25`, eller tarball under `~/Library/Java/JavaVirtualMachines/`).
- **Gradle 9.6.0** (wrapper) og **AGP 9.4.0**. JDK 25 er brukt ved verifikasjon.
- Sett `JAVA_HOME` til JDK 25, eller `org.gradle.java.home` i `~/.gradle/gradle.properties` / `android/gradle.properties`.
- App-kode kompileres fortsatt mot **Java 17** (`compileOptions` / `jvmTarget`).
- **Java 24:** Gradle 8.14+ løser tidligere «Type T not present» på unit tests; bruk JDK 25 + Gradle 9.5 for anbefalt oppsett.

For Google Sign-In: sett `GOOGLE_WEB_CLIENT_ID` i `android/app/build.gradle.kts` og `GOOGLE_CLIENT_ID` i `backend/.env`.

## CI

`.github/workflows/ci.yml` kjører på pull request og på push til `main` og
`feat/handlehjelp-p0`, med tre jobber:

| Jobb | Kommando |
|---|---|
| Backend | `python -m pytest -q` (SQLite-enhetstester + C00-kontrakter) |
| Backend PostgreSQL | `python -m pytest -m postgres -q` mot servicecontainer `postgres:16-alpine` |
| Android | `./gradlew assembleDebug testDebugUnitTest lintDebug` på Temurin JDK 25 |

Samme kontroller lokalt:

```bash
cd backend && .venv/bin/python -m pytest -q
cd backend && .venv/bin/python -m pytest tests/contracts/test_c00_contracts.py -q
# PostgreSQL-jobben: start container som beskrevet over, så
cd backend && PRISLAPP_POSTGRES_TEST_URL=postgresql+asyncpg://prislapp:prislapp@localhost:55432/prislapp_test \
  .venv/bin/python -m pytest -m postgres -q
cd android && ./gradlew assembleDebug testDebugUnitTest lintDebug
```

CI bruker kastbare testcontainere uten secrets. Ingen jobb deployer eller rører
produksjonsdata.

## Fase 1 status

- [x] Backend skeleton + Docker Compose
- [x] Auth API (register, login, google, me)
- [x] MinIO bucket-oppsett
- [x] Android skeleton + auth UI
- [x] Backend-tester + Android unit- og instrumenteringstester
- [x] Fase 2: kamera, opplasting, OCR (se under)

## Fase 2 status

- [x] Backend: receipts/stores/receipt_items modeller + migrasjon
- [x] Backend: POST/GET /receipts, MinIO-opplasting, Celery worker
- [x] Backend: RapidOCR med varelinjegruppering, Rema 1000 / Normal / Europris og generisk fallback
- [x] Android: CameraX, Room offline-kø, WorkManager-opplasting
- [x] Android: polling UI + gjennomgangsskjerm
- [x] Brukerbundet offline-kø med stabile opplastings-ID-er, gjenopptakelse og retry
- [x] Automatisk JWT-fornyelse for API-kall
- [x] Nytt OCR-forsøk for feilede kvitteringer
- [x] Sletting av originalbilder etter 30 dager og ved sletting av kvittering

## Fase 3 status

- [x] Backend: products/product_aliases/price_observations + migrasjon 003
- [x] Backend: PUT /receipts/{id}/confirm, DELETE /receipts/{id}
- [x] Backend: GET /products/search, GET /products/{id}/my-prices, GET /stores
- [x] Backend: listefilter på GET /receipts (butikk, status)
- [x] Android: redigerbar gjennomgangsskjerm + bekreftelse
- [x] Android: historikk med butikkfilter
- [x] Android: produktsøk og «billigst for meg»
- [x] Datoredigering, norske desimaltall og validering i gjennomgang
- [x] Paginert historikk med butikk- og datofilter
- [x] Pris per enhet, billigste observasjon og sist observerte pris per butikk
- [x] Konservativ produktnormalisering og fuzzy matching med bevaring av tall/størrelser

## Drift og migrasjoner

API-oppstart kjører Alembic automatisk, både i Compose og med Dockerfile i roten.
Migrasjon `004` omregner eksisterende prisobservasjoner fra linjesum til pris per enhet
og retter butikktilknytningen etter butikkredigering. Ta vanlig databasebackup før oppgradering.

`python -m scripts.run_migrations` tar en PostgreSQL advisory lock (`pg_advisory_lock`)
før stamping og `alembic upgrade head`. Starter to instanser samtidig, venter den andre
på låsen i stedet for å kjøre samme migrering parallelt. Andre dialekter (SQLite) kjører
uten lås.

Skjemaversjon **gjettes ikke** fra at en tabell finnes. `scripts/run_migrations.py`
verifiserer tabellene *og* kolonnene hver revisjon oppretter (`SCHEMA_REVISIONS`) før en
database som er bootstrappet med `create_all()` stampes, og stopper med
`MigrationStateError` hvis skjemaet bare er delvis på plass, mangler en tidligere
revisjon eller inneholder en revisjon som ikke er deklarert. Rene datamigreringer
(`DATA_ONLY_REVISIONS`, i dag `004`) etterlater ingen skjemaspor og kjøres på nytt etter
stamping; de må derfor være idempotente.

**Ny migrasjon:** legg skjemaendringer inn i `SCHEMA_REVISIONS` med tabell- og
kolonnenavn, eller revisjonen i `DATA_ONLY_REVISIONS` hvis den bare endrer data.
`tests/test_migrations.py` feiler hvis en revisjon i `alembic/versions/` ikke er
deklarert.

Compose starter også **scheduler** (Celery Beat). Ved separat Sliplane-deploy må både
worker og én scheduler kjøre med samme database-, Redis- og MinIO-konfigurasjon:

```bash
celery -A app.worker.celery_app worker --loglevel=info
celery -A app.worker.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule
```

Produksjon på Sliplane kjører fra 2026-09-10 scheduler innebygd i den ene worker-tjenesten:
`celery -A app.worker.celery_app worker --loglevel=info --concurrency=1 --beat --schedule=/tmp/celerybeat-schedule`.
Det skal ikke kjøres en ekstra Beat-instans samtidig med dette oppsettet.

Scheduler sjekker utløpte bilder hver time. Historikk beholdes når originalen utløper.
Android sletter den lokale bildekopien etter vellykket opplasting og rydder resterende
utløpte køelementer med WorkManager (kjøretid styres av Android).

Room oppgraderes fra versjon 1 til 2. Gamle køelementer uten kjent eier blir ikke
tilordnet en tilfeldig innlogget bruker; de holdes skjult og slettes av 30-dagersoppryddingen.
Nye bilder knyttes til kontoen som opprettet dem.

## Verifikasjon av fase 2 og 3

```bash
# Backend, inkludert OCR på bildene i testdata/
cd backend
.venv/bin/python -m pytest -q

# Valgfri ende-til-ende-test; URL må peke til en disponibel teststack.
# Testen oppretter en testkonto og sletter kvitteringene etterpå.
PRISLAPP_TEST_URL=http://localhost:18000 .venv/bin/python -m pytest tests/test_live_pipeline.py -v

# Android
cd ../android
./gradlew assembleDebug testDebugUnitTest lintDebug
./gradlew connectedDebugAndroidTest -PapiBaseUrl=http://10.0.2.2:18000/
```

UI-integrasjonstesten bruker bare den eksplisitte lokale test-URL-en på port 18000.
Databasetestene kjører uten backend. Google OAuth må fremdeles konfigureres som beskrevet
over. OCR-resultater skal alltid gjennomgås; generell splitting av flere kvitteringer
i ett bilde er utenfor MVP. Se [fase 2/3-leveransen](docs/superpowers/plans/2026-09-10-fase-2-3-ferdigstilling.md).
