# Prislapp – Systemdesign

**Status:** Godkjent  
**Dato:** 2026-08-04  
**Versjon:** 1.0

## Mål

En Android-app der brukeren fotograferer kvitteringer fra norske dagligvarebutikker (store kjeder og mindre lokale). Bildene sendes til en selvhostet backend som kjører OCR, parser butikk/produkter/priser, og lagrer i database. Brukeren kan opprette profil og se **sin egen** handlehistorikk, inkludert hvor de historisk har kjøpt et produkt billigst.

## Avklarte beslutninger

| Tema | Beslutning |
|------|------------|
| Plattform | Android (Samsung + Google Pixel, minSdk 26) |
| Marked | Norge – alle dagligvarebutikker |
| Hosting | Selvhostet (Sliplane / VPS) via Docker Compose |
| Backend-språk | **Python FastAPI** (se begrunnelse under) |
| Auth | E-post + passord og Google Sign-In |
| Offline | Ta bilde offline; opplasting når nett er tilbake |
| Varsling | Polling i appen (ingen push i MVP) |
| OCR-feil | Gjennomgangs-/redigeringsskjerm før endelig lagring |
| Bilde-lagring | Behold original 30 dager, deretter slett (GDPR) |
| Prissammenligning | **Kun brukerens egen historikk** – ingen aggregert data på tvers av brukere |

## Backend-språk: Python FastAPI

Valgt fordi OCR- og kvitteringspipeline er kjernen i produktet:

- Modne biblioteker: PaddleOCR, EasyOCR, Tesseract, OpenCV, Pillow
- Enkel iterasjon på butikk-spesifikke parsere (Rema, Kiwi, Coop, generisk fallback)
- Async API med FastAPI + Celery/ARQ for bakgrunnsjobber
- OpenAPI-generering gir gratis API-dokumentasjon til Android-klienten

Kotlin (Ktor/Spring) deles med Android-appen, men OCR-økosystemet er svakere og ville sannsynligvis krevd et separat Python-worker uansett.

## Systemarkitektur

```
┌─────────────────────────────────────────────────────────────┐
│  Android-app (Kotlin, Compose, MVVM, Hilt)                  │
│  CameraX → Room (offline-kø) → WorkManager → Retrofit API  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS + JWT
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI (REST)                                             │
│  Auth │ Receipt ingest │ Product compare │ Store lookup     │
└───────┬─────────────────────────────────────────────────────┘
        │
   ┌────▼────┐    ┌──────────┐    ┌─────────────┐
   │  MinIO  │    │PostgreSQL│    │ Redis+Celery│
   │ (bilder)│    │  (data)  │    │ (OCR-kø)    │
   └─────────┘    └──────────┘    └──────┬──────┘
                                          │
                                   ┌──────▼──────┐
                                   │ OCR Worker  │
                                   │ + Parser    │
                                   └─────────────┘
```

## Android-app

### Stack

- Kotlin, Jetpack Compose, MVVM, Hilt
- CameraX (kvitteringsfoto)
- Room (offline-kø, lokal cache, session)
- WorkManager (opplasting ved nett)
- Retrofit + OkHttp (API)
- StateFlow + collectAsStateWithLifecycle

### Skjermer (MVP)

1. **Innlogging/registrering** – e-post + passord, Google Sign-In
2. **Hjem** – siste kvitteringer, «Ta bilde»-knapp
3. **Kamera** – veiledning for god OCR-kvalitet
4. **Opplastingskø** – PENDING → UPLOADING → PROCESSING → READY / FAILED
5. **Gjennomgang** – rediger butikk, dato, produkter, priser
6. **Historikk** – kvitteringer filtrert på butikk/dato
7. **Produktsøk / billigst for meg** – se egne priser per butikk for ett produkt

### Offline-flyt

1. Bruker tar bilde → lagres lokalt (Room + filsystem), status `PENDING`
2. WorkManager venter på nettverk
3. Ved nett: `POST /receipts` (multipart) → status `PROCESSING`
4. App poller `GET /receipts/{id}` til status `READY_FOR_REVIEW`
5. Bruker bekrefter/redigerer → `PUT /receipts/{id}/confirm` → status `CONFIRMED`

### Polling-strategi

- Poll hvert 3. sekund mens kvittering er `PROCESSING` (aktiv skjerm)
- Poll hvert 30. sekund i bakgrunnen (WorkManager) for kø med ventende kvitteringer
- Eksponentiell backoff ved feil (maks 5 min)

## Backend

### Tjenester (Docker Compose)

| Tjeneste | Rolle |
|----------|-------|
| `api` | FastAPI REST-endepunkter |
| `worker` | Celery – OCR + parsing |
| `postgres` | Relasjonell database |
| `redis` | Celery broker |
| `minio` | S3-kompatibel bildelagring |

### API-endepunkter (MVP)

```
POST   /auth/register
POST   /auth/login
POST   /auth/google
GET    /auth/me

POST   /receipts                    # multipart: image + optional metadata
GET    /receipts                    # brukerens kvitteringer (paginert)
GET    /receipts/{id}               # status + parsed data
PUT    /receipts/{id}/confirm       # bruker bekrefter/redigerer
DELETE /receipts/{id}

GET    /products/search?q=          # søk i brukerens produkter
GET    /products/{id}/my-prices     # brukerens priser per butikk for produkt
GET    /stores                      # butikker bruker har handlet i
```

### OCR-pipeline

1. **Forbehandling** – rotasjon, kontrast, beskjæring (OpenCV)
2. **OCR** – PaddleOCR/EasyOCR (CPU, selvhostet)
3. **Butikk-gjenkjenning** – regex/keyword på header (butikknavn, org.nr)
4. **Linje-parsing** – butikk-spesifikke parsere + generisk fallback
5. **Produkt-normalisering** – lowercase, fjern spesialtegn, fuzzy match mot `product_aliases`

### Kvitteringsstatus

```
PENDING_UPLOAD → UPLOADED → PROCESSING → READY_FOR_REVIEW → CONFIRMED
                                        ↘ FAILED (bruker kan prøve på nytt)
```

## Datamodell

### Tabeller

- **users** – id, email, password_hash, google_sub, created_at
- **stores** – id, name, normalized_name, chain (nullable)
- **receipts** – id, user_id, store_id, purchase_date, total, status, image_path, image_expires_at, raw_ocr_text
- **receipt_items** – id, receipt_id, product_id (nullable), raw_product_name, quantity, unit_price, line_total
- **products** – id, canonical_name, category, ean (nullable)
- **product_aliases** – id, product_id, alias_name, store_id (nullable)
- **price_observations** – id, user_id, product_id, store_id, receipt_item_id, price, observed_at

All prishistorikk er **bruker-scopet** via `user_id` på `price_observations` og `receipts`.

### «Billigst for meg»-spørring

For et gitt produkt og bruker:

```sql
SELECT s.name, po.price, po.observed_at
FROM price_observations po
JOIN stores s ON s.id = po.store_id
WHERE po.user_id = :user_id AND po.product_id = :product_id
ORDER BY po.price ASC, po.observed_at DESC;
```

Vis billigste butikk, alle observasjoner, og sist observert pris per butikk.

## Personvern og sikkerhet

- HTTPS (Let's Encrypt)
- JWT access token (15 min) + refresh token (7 dager)
- Passord: bcrypt/argon2
- MinIO privat bucket; signerte URL-er med kort levetid
- Bilder slettes automatisk etter 30 dager (`image_expires_at`)
- Bruker kan slette konto og all tilknyttet data (GDPR)
- Ingen deling av data mellom brukere

## Teststrategi

### Android

- Unit: ViewModels, use cases
- Integrasjon: Room, Retrofit (MockWebServer)
- UI/Screenshot: Roborazzi på Compose-skjermer

### Backend

- Unit: parsere per butikkformat (pytest)
- Integrasjon: API + database (testcontainers)
- OCR-regresjon: anonymiserte eksempelkvitteringer i `testdata/receipts/`

## Byggerekkefølge (MVP)

1. **Fase 1 – Fundament** (parallelt)
   - Backend: FastAPI skeleton, auth, PostgreSQL, MinIO, Docker Compose
   - Android: prosjektstruktur, auth, grunnleggende navigasjon

2. **Fase 2 – Kjerne**
   - Android: CameraX, offline-kø, WorkManager-opplasting
   - Backend: OCR worker, parser for 1–2 butikkformater + generisk fallback

3. **Fase 3 – Brukerverdi**
   - Gjennomgangsskjerm (Android)
   - Historikk og «billigst for meg»-søk
   - Parser-utvidelse basert på eksempelkvitteringer

## Eksempelkvitteringer

Anonymiserte kvitteringsbilder lagres i `testdata/receipts/` i repoet (gitignored hvis de inneholder sensitiv info) og brukes til:

- OCR-kvalitetsvurdering
- Butikk-spesifikke parsere
- Regresjonstester

## Åpne punkter for implementasjonsplan

- Eksakt Docker/hosting-oppsett på Sliplane
- Valg mellom PaddleOCR og EasyOCR (benchmark med eksempelkvitteringer)
- Detaljert Compose-navigasjonsgraf
- CI/CD pipeline
