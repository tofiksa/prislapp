# OCR-00 — fasit og reproduserbar kvalitetsmåling

## Selvstendig oppdrag

Prislapp er en FastAPI-backend som bruker RapidOCR på egne kvitteringer før manuell bekreftelse. Brukeren opplever feil butikknavn og totalsum. Dagens bildetester sjekker hovedsakelig at noen varer og en total finnes. En beregnet varesum skjuler derfor avlesningsfeil.

Arbeid i `~/workprojects/prislapp/backend`. Les `../docs/ocr-backend/README.md`. Baseline `4bb0dcb`; sjekk faktisk kode. **Ingen avhengigheter.** Lever et målegrunnlag; ikke endre parseroppførsel i denne oppgaven.

## Les først

- `tests/test_receipt_images.py`, `tests/test_ocr_service.py`, `tests/test_rema1000_parser.py`.
- `app/services/ocr_service.py`, `app/parsers/{base,generic,rema1000,retail}.py`.
- `../testdata/receipts/README.md` og de tre eksisterende bildene.
- `requirements.txt` og `../README.md` for testmiljø.

## Leveranse og steg

1. Lag `tests/fixtures/ocr/` med minst de seks eksakte feilinputene fra planens kapittel 3, og ytterligere tilfeller for delt etikett/beløp, MVA, kontant/vekslepenger, ukjent butikk, tomtekst og motstridende totaler. Merk om fasiten er verdi eller forventet avståelse.
2. Definer en versjonert fasitstruktur: fixture-ID, bilde/tekst/layout-referanse, original-/variantgruppe, split, kjede, filialtekst, trykt total som desimalstreng/null, feltets lesbarhet og kildeområde/-tekst. Ikke hardkod fasit i kjedeparseren.
3. Skill `readable`, `absent`, `unreadable`, `cropped`, `multi_document`. «Total skal være null» er en gyldig fasit. Europris/Normal-bildet får vurdert dokumentomfang, ikke automatisk total 39,90 som fasit for hele bildet.
4. Legg verifisert fasit på de to hele eksisterende bildene: Rema Metro Senter 158,83 / 7 varer; Normal Oslo, Thon Senter Triaden 100,00 / 6 varer. Bekreft mot selve bildene, ikke parseroutput.
5. Lag `scripts/benchmark_receipts.py` med to moduser: parser på fasittekst/layout og bilde→OCR→parser. Kommandoen virker lokalt uten DB/MinIO og lager deterministisk maskinlesbar rapport til eksplisitt valgt lokal fil. Ingen råtekst/bilder i standardrapport.
6. Rapportér eksakt total, kjede og filial separat, akseptert-felt-presisjon, dekning, avståelser, falske sikre treff, beløpsavvik og tid. Endelig total måles aldri med «innen noen kroner»-toleranse. Bruk eksakt Decimal til øret.
7. Registrer modell-ID/hash, OCR-/parser-/preprocessversjon, plattform, CPU/minne og Git-revisjon. En motor som ikke tilbyr confidence får `null`, ikke fabrikkert score.
8. Lag dokumentert innsamling/merking for minst 30 unike, samtykkede/anonymiserte kvitteringer fra minst tre målgruppekjeder. Mangler bilder, lever verktøyet og rapportér datablokkeringen; ikke finn på eksempelbilder eller målte resultater.

## Tester og akseptanse

- Måleverktøy testes mot faste falske prediksjoner med kjent precision/coverage og nullfelt. Det skal ikke gi 100 % ved å avstå fra alle felt.
- Identiske bilder eller bearbeidede varianter havner ikke i både utviklings- og holdoutsett.
- Nåværende bugs registreres i benchmark og forventet-feil-regresjoner med konkrete grunner; ikke gjør hele standard-CI rød permanent eller skjul dem med udokumentert `xfail`. Oppgave 02/03 fjerner tilsvarende forventet-feil når løst.
- En rapport kan reproduseres med oppgitt kommando og samme artefakter. Testbilder behandles lokalt.

Kjør eksisterende målrettet pakke:

```bash
.venv/bin/python -m pytest tests/test_ocr_service.py tests/test_receipt_images.py tests/test_rema1000_parser.py -q
```

Legg nye benchmark-/fixturetester til kommandoen og dokumenter det faktiske CLI-et du implementerer. Ikke påstå kvalitetsgevinst før parserendringer er målt.

## Avgrensning og overlevering

Ingen DB-migrasjon, ny OCR-motor eller ekstern API. Dette verktøyet skal gjenbrukes av alle oppgavene. Lever `docs/ocr-backend/handoffs/OCR-00.md` fra repo-roten med fixturemanifest, baseline, kjørekommando, uløste feil og manglende data. Legg ikke private kvitteringstekster i overleveringen.
