# Feilkontrakt, idempotens og offline

## Feilformat

Alle nye v2-feil (og nye auth-ruter) bruker:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "Trygg, brukerrettet tekst uten intern detalj.",
  "field_errors": [{ "field": "expected_version", "code": "stale_version", "message": "…" }],
  "retryable": false,
  "request_id": "req_…"
}
```

- Ingen OCR-tekst, tokens, e-postinnhold eller stacktrace i `message`, `field_errors` eller loggfelter som kan nå klienten.
- `retryable=true` bare for nett/timeout/429/5xx der ny forespørsel er meningsfull.
- Eksempel: `fixtures/error-409-version.json`.

Eksisterende v1-ruter kan fortsatt returnere FastAPI `detail` inntil de byttes; nye klientkall skal bruke v2.

## Idempotens

- Mutasjoner har klientgenerert `mutation_id`.
- Nye ressurser kan ha klientgenerert UUID for offlinebruk.
- Nøkkel: `(user_id, operation, mutation_id)`.
- Samme nøkkel + samme payload-hash → samme resultat (200/201 med original ressurs).
- Samme nøkkel + annet innhold → **409**.
- `expected_version` som ikke matcher → **409** med gjeldende versjon. Ingen last-write-wins.

Opplasting av kvitteringsbilde: like nøkkel og like fil-hash → én kvittering. Like nøkkel og ulik fil → 409.

### Kvitteringsopplasting (v1 `POST /receipts`)

Header `Idempotency-Key` er receipt-UUID. Payload-hash er SHA-256 av rå filbytes (hex 64), lagret på `receipts.payload_hash`.

- Samme bruker, samme nøkkel, samme hash → 201 med original id/status. Ingen ny OCR-jobb hvis den allerede er queued/processing/done.
- Samme nøkkel, annen fil → **409** `IDEMPOTENCY_CONFLICT` (C00). Originalen overskrives ikke.
- Uten nøkkel: ny UUID som i dag. Hash lagres likevel.

Låste filgrenser, sjekket **før** `create_receipt` / `job_outbox` / `process_receipt`. Ingen stille nedskalering:

| Grense | Verdi | Feil |
|---|---|---|
| Rå fil | 20 MiB | 413 (eksisterende v1 `detail`) |
| Dekodet piksler (bredde×høyde) | 40_000_000 | 413 `IMAGE_TOO_LARGE` (C00, `retryable=false`) |
| Maks side | 12_000 px | 413 `IMAGE_DIMENSIONS` (C00, `retryable=false`) |
| Format etter dekoding | JPEG, PNG | 400 v1 `Invalid image` |

PDF/HTML/tom fil avvises som i dag (400). Nye 409/413-ruter bruker C00 `{code, message, field_errors, retryable, request_id}`. Ingen OCR-tekst i `message`.

## Paginering

Cursor + stabil sekundærsortering på ID. Standard 50, maks 100.

## Offline og konflikt (Android)

1. Lokal handling lagres transaksjonelt i Room/outbox **før** UI bekrefter.
2. Mutasjoner sender eksplisitte feltverdier, aldri «toggle».
3. Uavhengige linjeendringer kan synkes separat. Konflikt på samme linje viser lokal vs server; bruker velger. Aldri stille overskriving av mengde eller sletting.
4. Konflikt mellom server-arkiv/slett og lokal redigering: behold lokal utgave som gjenopprettbart utkast. **Ikke** gjenoppliv en slettet serverliste automatisk.
5. Utløpt sync-cursor krever fullt snapshot. Ventende lokale endringer bevares og avklares før replay.
6. Prisrespons er avledet. Den kan feile uten at listen blir utilgjengelig.
7. Batchprising skjer først etter at lokale endringer er synket og `list_version` er kjent. Ellers merket cache eller «Pris oppdateres etter synkronisering».
8. Eldre `calculated_at` / lavere `list_version` skal ikke erstatte nyere UI-tilstand.
9. Ved logout: skjul data straks, stopp workers for kontoen, rydd bilde-/token-cache. Uopplastede kvitteringer krever eksplisitt valg før lokal sletting.
10. Kontoavgrenset database. Ingen ventende mutasjoner sendes med en annen kontos token.
