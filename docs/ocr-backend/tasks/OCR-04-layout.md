# OCR-04 — strukturert OCR, leserekkefølge og seksjoner

## Selvstendig oppdrag

Prislapp bruker RapidOCR 3.9.2. `OcrService.extract_text` beholder bare en streng etter enkel y-gruppering av bokser. Totaletikett og beløp kan splittes, og betaling/MVA kan blandes med varer. Vi trenger geometri og kildebevis for mer robust butikk-/totalgjenkjenning.

Arbeid i `~/workprojects/prislapp/backend`; baseline `4bb0dcb`. Les `../docs/ocr-backend/README.md` og **OCR-01-kontrakten/overleveringen**, som er nødvendig. OCR-00 leverer testbilder; denne oppgaven kan starte med syntetiske layoutfixtures.

## Filer og omfang

Eier `app/services/ocr_service.py` sin motoradapter og ny `app/parsers/layout.py`. Les `requirements.txt`, `tests/test_ocr_service.py` og `app/parsers/base.py`. Bildetransformasjoner utover eksisterende EXIF/resize eies av OCR-05.

## Implementasjonssteg

1. Verifiser faktisk RapidOCR-resultat-API for den pinnede versjonen: tekst, polygoner, scorer og modellinfo. Ikke anta navn/format eller at alle array har lik lengde. Dokumenter adapteren med testdouble og minst én virkelig kjøring.
2. Innfør `extract_document(bytes)` etter OCR-01-kontrakten. `extract_text` forblir kompatibel wrapper med deterministisk tekstserialisering.
3. Behold original og normalisert tekst, token-ID, polygon, valgfri score og kildepass. Konverter geometri til EXIF-orientert original med korrekt skaleringskart. Test også manglende geometri/score.
4. Bygg rader ut fra vertikal overlapp/baselinjer og skrifthøyde, ikke bare avstand til første token i siste rad. Bevar separate kolonner og beløpsrelasjoner; ulik skrifthøyde i totalfelt skal ikke splitte sikkert sammenhørende tekst unødvendig.
5. Finn myke seksjonsgrenser: header, varer, totalsone, betaling, MVA og footer. Kombiner posisjon og etiketter; «nederst = total» er utilstrekkelig. Ukjent seksjon er tillatt.
6. Returner relasjoner som lar OCR-02 finne etikett og verdi på samme/neste rad. Ikke velg handelssummen her; layout og felttolking skal kunne testes separat.
7. Marker konkurrerende dokumentregioner/leserekkefølge. Ikke lov robust dokumentdeteksjon fra én heuristikk; sikre tilfeller kan stoppes, usikre returneres med advarsel.
8. Begrens tokenmengde, dimensjoner og serialisert payload. Ugyldig motoroutput skal gi kontrollert kvalitets-/motorfeil, ikke usanitert dump av hele kvitteringen.

## Obligatoriske tester

- Etikett venstre og beløp høyre, stor totalfont, skrå rad, to nærliggende varelinjer, flere beløpskolonner i MVA-tabell.
- Tokens leveres i ulik rekkefølge, men gir samme layout. Like y-koordinater med forskjellig x gir stabil rekkefølge.
- Polygoner etter EXIF-rotasjon og nedskalering peker tilbake til riktig originalområde.
- Null/tomme array, manglende score, uventet lengdeavvik og NaN i koordinater gir dokumentert feil/fallback.
- Eksisterende syntetiske OCR-bildetester og de to hele kvitteringene fortsetter å kunne leses.
- Tokenbevis peker til eksisterende token-ID og blir ikke feil ved wrapperbruk.

## Ferdigkriterier

Ny strukturert adapter fungerer med RapidOCR og uten database. Output er deterministisk for samme motorresultat. Testene må vise at betalings-/MVA-kolonner ikke er flattet inn i varetekst på en måte som gjør senere klassifisering umulig. Ikke skjul regresjon ved bare å teste at teksten er ikke-tom.

Kjør nye layout-/adaptertester, `tests/test_ocr_service.py`, `tests/test_receipt_images.py` og OCR-00 benchmark hvis tilgjengelig. Rapporter modellartefakt og faktisk dimensjonsendring.

Lever `docs/ocr-backend/handoffs/OCR-04.md` med adapterkontrakt, koordinatsystem, relasjoner, testresultater og hvilke deler OCR-05 kan endre. Ingen worker-/DB-endringer eller modellbytte.
