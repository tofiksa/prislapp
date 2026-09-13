# OCR-03 — butikk, kjede og filial fra faktisk kvitteringsbevis

## Selvstendig oppdrag

Prislapp bruker i dag første tekstlinje som butikk i generisk parsing. Rema krever `REMA 1000 <filial>` på én linje. Dermed blir `VELKOMMEN` butikk, og logo/kjedenavn over filial gir manglende navn selv med korrekt tekst. Brukeren ønsker at butikk identifiseres pålitelig.

Arbeid i `~/workprojects/prislapp/backend`; baseline `4bb0dcb`. Les `../docs/ocr-backend/README.md`, OCR-01-kontrakten og overleveringene fra **OCR-00 + OCR-01**.

## Les først og eierskap

- `app/parsers/{generic,rema1000,retail,__init__}.py`.
- Eksisterende private butikkmodeller/tjenester i `app/models/` og `app/services/`; finn dem fra faktisk kode, ikke anta at bare legacy `Store` finnes.
- `../docs/contracts/ADR-001-privat-produktidentitet.md`, `datamodell.md`.

Lag en ren kandidatmodul `app/parsers/store_detection.py` og et lite, versjonert kjedealiasregister. OCR-06 eier dispatcher; OCR-07 eier privat lagring. Unngå DB-oppslag direkte fra tekstparseren.

## Krav og algoritme

1. Samle butikkbevis fra header, tilgrensende linjer og eventuelt gjentatt kjøpmannsnavn på terminaldelen. Lag kandidat før du velger vareparser.
2. Støtt kjedenavn på egen linje og filial på neste relevante linje, men ikke anta at enhver neste linje er filial. Juridisk selskap, adresse, telefon, org.nr., `Salgskvittering` og `Velkommen` klassifiseres separat.
3. Skille `chain`, `branch_text` og `resolved_user_store_id`. Et sted som «Oslo» eller kjedenavn alene er ikke tilstrekkelig til å verifisere en bestemt filial.
4. Smalt aliasregister for dokumenterte kjeder/variasjoner. Legg til Rema, Normal og Europris som regresjonsgrunnlag, samt kjeder fra nye testdata. Støtte for å kjenne kjedenavn er ikke det samme som dokumentert vareparserstøtte.
5. OCR-forvekslinger (`REMA l000`, `R EMA 1000`) håndteres med kontrollert navnekontekst. Ikke bruk aggressiv fuzzy på alle linjer, og ikke velg Normal fordi en vare heter «normal».
6. Logo kan gi kjede, men ikke filial. Hvis filial er borte, returner `chain_only` + `BRANCH_UNRESOLVED`, ikke en oppfunnet avdeling.
7. Brukerens egne tidligere bekreftede butikkaliaser kan leveres inn som separat kontekst. Automatisk kobling krever tilstrekkelig samsvar med nåværende kvitteringsbevis. Bruk aldri bare «brukeren handler vanligvis der» som fasit.
8. Ikke slå sammen filialer fra samme kjede. Org.nr. kan tilhøre flere filialer og er ikke alene unik butikk-ID.
9. To konkurrerende butikkheadere/dokumenter gir `MULTIPLE_DOCUMENTS` eller usikker butikk, ikke tekst fra to kvitteringer kombinert til ett navn.
10. Returner kildetokens/linjer, regel-ID, kandidater og usikkerhetsårsaker. Bevar eksakt observert tekst ved siden av kanonisk kjedenavn.

## Tester

- `REMA 1000\nMETRO SENTER` gir filialkandidat; `REMA 1000\nSalgskvittering` gir bare kjede.
- `VELKOMMEN\nKIWI OSLO` blir ikke «VELKOMMEN» og blir ikke uten videre en unik Oslo-filial.
- Normal-eksemplet bevarer `Normal Oslo, Thon Senter Triaden`; EP + filial på egen linje støttes når konteksten er entydig.
- Header-logo feilavlest, men tydelig kjøpmannsnavn gjentatt nedenfor; ingen kjede gjettes ut fra ett vareprodukt.
- Samme juridiske eier på to adresser, butikktekst kun i footer, manglende header og avskåret bilde.
- To brukere med samme råtekst og forskjellige private koblinger påvirker ikke hverandre; test med injisert kontekst uten produksjonsdatabase.
- To kvitteringer i ett dokument gir usikkerhet fremfor sammenslåing.

## Akseptanse og overlevering

Kjede og filial evalueres separat med OCR-00. Kritiske negative tilfeller har ingen falsk sikker filial. Modulen virker med strukturert layout-fixture og tekst-only-adapter. Ukjent kjede fungerer fortsatt som ukjent/generisk, ikke fatal feil.

Kjør `tests/test_store_detection.py` (ny), relevant parserpakke og parserbenchmark. Dokumenter at full bildeintegrasjon skjer i OCR-06/07. Lever `docs/ocr-backend/handoffs/OCR-03.md` med offentlige funksjoner, aliasregisterets kilde/versjon, testresultater og alle uavklarte tilfeller. Ingen global katalogpopulering, ekstern butikk-API eller Androidendring.
