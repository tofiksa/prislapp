# OCR-05 — lesbare lange kvitteringer og begrenset andrepass

## Selvstendig oppdrag

Prislapp begrenser i dag lengste bildeside til 2500 px. Det kan gjøre teksten på en lang kvittering svært liten, selv om originalen er skarp. Et lite kjedelogofelt eller totalfelt kan også feile uten at hele kvitteringen trenger ny OCR.

Arbeid i `~/workprojects/prislapp/backend`. Les hovedplanen, kontrakten og handoffs for **OCR-00, OCR-01 og OCR-04**. Oppgaven er P1, men kan prioriteres tidligere hvis baseline viser mange avlesningsfeil på lange bilder.

## Les først og eierskap

- `app/services/ocr_service.py`, eksisterende opplastingsvalidering i `app/routers/receipts.py` og `tests/test_receipt_upload_limits.py`.
- `app/config.py` for lease/budsjett.
- OCR-04 sin transform-/layoutkontrakt.

Legg bildepolicy i egen modul, eksempelvis `app/services/receipt_image_preprocessing.py`. Koordiner adapterendringer med OCR-04; ikke rediger samtidig.

## Krav

1. Mål nåværende resize på både normale og syntetisk lange bilder. Bruk tekst-/dokumentbredde som kvalitetsindikator, ikke bare lengste side.
2. Behold original bytes uendret. Normaliser EXIF én gang. Eventuell dokumentbeskjæring må bevare topp/bunn og ha konservativ fallback til hele bildet når kantene er usikre.
3. Langkvitteringer kan deles i overlappende utsnitt med bevart tekstskala. Sett tak på samlet pikselmengde/antall utsnitt. Dedup tokens i overlapp ved posisjon+tekst, uten å fjerne to identiske varer som faktisk står på ulike rader.
4. Test forsiktig deskew/perspektiv- eller kontrastbehandling som alternative pass, ikke alltid alle filtre på alle bilder. Svak varmeprint kan bli verre av terskling; standardpasset skal beholdes til sammenligning.
5. API for målrettet andrepass mottar usikker header-/totalregion fra pipeline. Bruk fulloppløselig kilde, margin rundt feltet og maks to utsnitt i ett andrepass. Ikke velg bare nederste kvartal; total kan ligge før lang terminal/footertekst.
6. Krysspass-sammenligning skjer på feltkandidater og bevis. To motstridende pass blir ikke automatisk sikre fordi ett har høyere rå OCR-score.
7. Default budsjettforslag: maks 45 sekunder veggklokketid for hele OCR-kjøringen, maks ett andrepass, samt eksplisitt ressurs-/tilegrense. Sett faktisk tall i konfig etter måling. Native ONNX-kall må kunne stoppes/isoleres; `asyncio.wait_for` alene stanser ikke CPU-koden.
8. Timeout skal returnere beste trygge delresultat hvis tilgjengelig, ellers kontrollert feil. Ikke retry permanent uleselig bilde fem ganger uten forskjell i input/policy.

## Tester og måling

- Lang kvittering, mørk bakgrunn, svakt trykk, uskarpt bilde, 90° uten EXIF, moderat skråstilling og avskåret topp/bunn.
- Geometrien mappes korrekt tilbake gjennom rotasjon, crop og resize.
- Overlapp dedupliserer samme token uten å miste repeterte varelinjer.
- Klokke-/inferensfake beviser budsjett og passgrense; integrasjon viser håndtering av faktisk prosess som henger. Token-/minnegrenser testes på store gyldige bilder.
- Sammenlign mot baseline på samme holdout og navnfestet maskin: total-/butikkpresisjon og coverage, p50/p95, minne og kaldstart. En mer komplisert preprocess aktiveres ikke hvis gevinst ikke er vist.

## Overlevering

Lever `docs/ocr-backend/handoffs/OCR-05.md` med valgt policy, målte resultater, ressurstak, runtime-avhengigheter, koordinatbevis og hvordan OCR-06/07 skal aktivere andrepass. Ingen ny ekstern OCR-tjeneste, automatisk produksjonsreprosessering eller fler-kvitteringsstøtte. Hvis ingen kandidat forbedrer kvaliteten, er en dokumentert negativ evaluering gyldig; ikke slå på en dårligere policy for å «levere funksjonen».
