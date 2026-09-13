# OCR-07 — sikker worker-, lagrings- og reviewintegrasjon

## Selvstendig oppdrag

Prislapp har allerede outbox, attempt-fencing, private v2-domener og kvitteringsrevisjoner. OCR går likevel via legacy `Receipt.total` og `Store`. Ny feltgjenkjenning skal bli synlig i review uten å miste proveniens eller overskrive brukerens endringer.

Arbeid i `~/workprojects/prislapp/backend`; baseline `4bb0dcb`. Les hovedplanen, OCR-01-kontrakten og handoffs fra **OCR-01 og OCR-06**. OCR-05 er tillegg hvis aktivert. Dette er eneste OCR-oppgave som eier migrasjon/worker/DB/API.

## Les først

- `app/worker/tasks.py`, `app/services/ocr_outbox.py`, `app/services/receipt_service.py`.
- `app/models/{receipt,receipt_revision,job_outbox}.py`.
- `app/services/{receipt_revision_service,receipt_revision_backfill}.py`.
- `app/schemas/{receipt,receipt_v2}.py`, `app/routers/{receipts,receipts_v2}.py`.
- `tests/test_{receipt_worker,job_outbox,receipt_image,receipt_reconciliation,v2_receipt_revisions}.py` og `tests/postgres/`.
- `scripts/run_migrations.py`, migrasjonskonvensjoner i `../README.md`, `../docs/contracts/`.

## Leveranse

1. Worker bruker ny strukturert pipeline og sender valg, kandidater, kvalitet og versjoner gjennom eksisterende `complete_ocr_result`. Bevar token-/attempt-/eierkontroll; ikke innfør en ny uavhengig kø.
2. Additiv lagring av siste OCR-ekstraksjon og eventuelt begrensede forsøk, knyttet til kvittering/eier/attempt. Begrens størrelse og bruk egne felt/tabell fremfor ubegrenset loggblob. Nyeste migrasjonsnummer bestemmes fra faktisk head, ikke fra denne planen.
3. Legacy `Receipt.total` fylles bare fra akseptert trykt total i ny pipeline; null ved usikkerhet. Eksisterende nullable respons bevares. `computed_items_total` kan bare vises via eksplisitt metadata, aldri maskeres som trykt total.
4. Undersøk faktisk v2-reviewlesing og eksponer additive `extraction`-metadata på relevant detaljrespons. Dokumenter eventuell nødvendig ny v2-leserute kun hvis eksisterende API mangler den. Oppdater OpenAPI/fixtures og kontrakttester.
5. Butikkforslag lagres kvitterings-/brukerbundet. Ikke opprett nye globale butikker fra usikre OCR-headere. For v1: en eksisterende trygg butikkreferanse kan beholdes, ellers returneres null + forslag i metadata. Dokumenter klientkonsekvensen. For v2 skal privat butikk-ID ikke oppfinnes av parseren.
6. Ikke bruk OCR som automatisk bekreftet revisjon. Kopiering til reviewkladd må beholde `printed_total` kontra beregnet sum og dato-/enhetsusikkerhet. Legacy historikk får `legacy_unknown` proveniens; ikke backfill den som sikkert avlest. Undersøk eksisterende revisjonsbackfill så nye beregnede verdier ikke feilaktig blir `printed_total`.
7. Autorisasjon/fencing: lås og revalider konto, kvittering, attempt og relevant status ved fullføring. Et gammelt/kansellert forsøk må ikke overskrive reviewkladd/bekreftet revisjon eller reopprette slettede data. Manglende kvittering gir ingen orphan-ekstraksjon.
8. Klassifiser motorfeil, timeout og uleselig bilde med trygge koder. Ikke fang/serialiser hele råkvitteringen i exception logging. Gjør kvalitetsmangel til review-advarsel når det finnes brukbare data, ikke evig retry.
9. Nye tokens, utsnitt og råfelt følger foreslått 30-dagers opprinnelig bildefrist. Råtekst som dupliseres i extraction må slettes samme sted. Retry forlenger ikke frist. Kvitteringssletting/kontosletting må omfatte nye artefakter; objektlagerfeil bruker eksisterende gjenoppretting eller eksplisitt retryjobb.
10. Ingen automatisk reprosessering av bekreftede kvitteringer. Eventuelt fremtidig «tolk på nytt» må være forslag med revisjonskontroll og krever egen brukerflyt.

## Tester og ferdigkriterier

- Worker→database→faktisk HTTP-detalj returnerer riktig butikkforslag og trykt total på golden fixtures, pluss kildereferanser. Test det API-et klienten faktisk bruker.
- V1-konsument uten kjennskap til metadata tåler både kjent og null total/butikk. Nye felter bryter ikke eksisterende C00-fixtures ukontrollert.
- `printed_total=null` med computed sum gir ikke falsk `BALANCED` eller automatisk prisgrunnlag.
- To samtidige forsøk, tapt lease, confirm/draft under OCR, sletting under OCR og konto deaktivert etter claim. Verifiser på PostgreSQL; SQLite er ikke bevis for låsing.
- Metadataretention, sletting, størrelsegrenser, rollback og misligholdt bevisreferanse. Gamle rader uten metadata fungerer.
- Frisk DB→head og eksisterende head→ny migrasjon, inkl. registrering i `SCHEMA_REVISIONS`/tilsvarende faktisk konvensjon.

Kjør målrettede tester, hele `.venv/bin/python -m pytest -q`, kontrakttestene og PostgreSQL-pakken mot disponibel testinstans som beskrevet i repoets README. Ingen produksjons-URL. Hvis nødvendig miljø mangler, registrer blokkering i stedet for å hevde fullført verifikasjon.

Lever `docs/ocr-backend/handoffs/OCR-07.md` med migrasjon, API-eksempler uten persondata, v1/v2-mapping, retention, tester, rollout-/rollbackrekkefølge og eksplisitt hva senere Android må gjøre for å vise advarsler.
