# OCR-01 — kontrakt for strukturert OCR og feltbevis

## Selvstendig oppdrag

Prislapp leser kvitteringer med RapidOCR, flater resultatet til tekst og mister posisjon/score. Butikk og total velges av enkle kjedeparsere. Vi trenger en felles, liten kontrakt som lar andre agenter forbedre teksttolking, layout og bilder uten å endre hverandres kode.

Arbeid i `~/workprojects/prislapp`. Les `docs/ocr-backend/README.md`. Baseline `4bb0dcb`. **Ingen implementasjonsavhengighet; koordiner fixtures med OCR-00.** Denne oppgaven eier kontrakten, ikke butikk-/totalalgoritmene.

## Les først

- `backend/app/services/ocr_service.py`, `backend/app/parsers/base.py`.
- `backend/app/models/receipt_revision.py`, `backend/app/schemas/receipt_v2.py`.
- `docs/contracts/{README,penger-og-avrunding,klientovergang}.md`.
- `backend/app/domain/{money,units}.py`.

## Leveranse

Opprett en minimal typet intern modell, foreslått `backend/app/domain/receipt_extraction.py`, og `docs/ocr-backend/contracts.md` med JSON-eksempler og kompatibilitetsbeslutninger.

Definer minst:

- `OcrDocument`: schema-/engine-/model-/preprocessversjon, originaldimensjoner, side-/dokument-ID, tokens, regioner og diagnostikk.
- `OcrToken`: stabil token-ID innen kjøring, originaltekst, valgfri OCR-score, polygon i normaliserte koordinater på EXIF-orientert originalbilde, kildepass/utsnitt. Transformasjon fra hvert utsnitt lagres eller kan reproduseres.
- `OcrLine`/seksjon: token-ID-er, leserekkefølge og `header|items|totals|payment|tax|footer|unknown`, uten å kreve at alle tokens har sikker seksjon.
- Feltkandidat: typet verdi, bevis-token-ID-er, regel-ID, OCR-score og separat rangeringsscore. `accepted|uncertain|missing`, årsakskoder, valgt kandidat-ID eller null. Scorer skal ikke omtales som sannsynlighet uten kalibrering.
- Butikk: kjede, observert filialtekst, valgfri privat butikk-ID, `branch|chain_only|unknown`. Ukjent filial og gjenkjent kjede skal kunne eksistere samtidig.
- Total: `printed_total`, `computed_items_total`, valuta/ukjent, `computed_items_complete`, avstemmingsstatus, kandidater og negative bevis. Pengetekst i JSON er desimalstreng.
- Foreslåtte årsaker: `TOTAL_NOT_FOUND`, `TOTAL_AMBIGUOUS`, `TOTAL_ITEMS_MISMATCH`, `ITEMS_INCOMPLETE`, `STORE_UNRESOLVED`, `BRANCH_UNRESOLVED`, `MULTIPLE_DOCUMENTS`, `IMAGE_TOO_SMALL`, `OCR_TIMEOUT`.
- Proveniens: kjørings-ID, attempt-ID ved lagring, pipelineversjon, metadataretention og gyldig referanse til kildetokens.

## Kompatibilitet

1. Behold `OcrService.extract_text(bytes)` som wrapper og `parse_receipt_text(str)` som inngang for eksisterende tester/brukere. Ny strukturert inngang er en egen metode; overgang skjer i OCR-06/07.
2. Tekst uten bokser skal kunne representeres med linje-ID-er og ukjent geometri. Ikke fabrikkér bokskoordinater.
3. `ParsedReceipt.total` skal i den nye flyten bety valgt trykt total eller null. Beregnet sum flyttes til separat felt. Dokumenter legacyadferden som endres og kontrakttestene som må oppdateres.
4. Et additivt `extraction`-felt på eksisterende kvitteringsdetalj kan foreslås; ingen ny leserute opprettes uten å undersøke hva v1/v2 faktisk har. Eldre klienter skal fortsatt få lovlige nullable felt.
5. OCR-forslag blir ikke bekreftet revisjon eller prisobservasjon. Eksisterende revisjonsmodell og pengepolicy forblir autoritative.

## Tester og ferdigkriterier

- Roundtrip serialisering for norsk tekst, Decimal, null-score, ukjent dato, polygoner og tokens fra flere utsnitt.
- Valider ugyldige koordinater/NaN/Infinity og brutte bevisreferanser uten å krasje worker ukontrollert. Grenser for tokentall/payload defineres.
- Eksempler: sikker total, delt etikett/beløp, beregnet sum uten trykt total, kjede uten filial, motstridende totaler og to dokumenter.
- Migrasjon/lagring er kun design i denne oppgaven; ikke velg et Alembic-nummer for OCR-07.

Kjør nye kontrakttester og `backend/tests/contracts/`. Dokumenter eksakte kommandoer fra `backend/`.

Lever `docs/ocr-backend/handoffs/OCR-01.md` med låste typer, eksporterte symboler, fixtures og endringer andre oppgaver må gjøre. OCR-02/03/04 skal kunne starte fra denne briefen og kontrakten uten tidligere chat.
