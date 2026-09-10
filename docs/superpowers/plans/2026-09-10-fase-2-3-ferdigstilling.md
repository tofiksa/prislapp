# Fase 2 og 3 – ferdigstilling

Grunnlag: godkjent systemdesign fra 2026-08-04 og kontroll av implementasjonen 2026-09-10.

## Fase 2 – kjerne

- [x] CameraX med feilmeldinger, kamerafrigjøring og veiledning.
- [x] Galleriimport på IO-tråd og håndtering av lesefeil.
- [x] Room-kø med eier, stabil capture-ID og migrasjon 1 → 2.
- [x] WorkManager-opplasting med nettverkskrav og retry uten duplikatkvitteringer.
- [x] API avviser feil bildedata, filer over 20 MB og ugyldige UUID-er.
- [x] Automatisk fornyelse av access-token med refresh-token.
- [x] Celery OCR med sen acknowledgement, transaksjonslås og beskyttelse mot duplikatjobber.
- [x] RapidOCR grupperer tekstbokser til varelinjer.
- [x] Rema-, Normal- og Europris-parser samt konservativ generisk fallback.
- [x] Aktiv polling hvert tredje sekund og bakgrunnspolling med 30–300 sekunders intervall.
- [x] Nytt OCR-forsøk for FAILED når originalen fortsatt finnes.
- [x] Automatisk opprydding av utløpte bilder i backend og lokalt.

## Fase 3 – brukerverdi

- [x] Gjennomgang med butikk, kjøpsdato, total og redigerbare varelinjer.
- [x] Norske desimaltall og eksplisitt validering av antall/pris/navn.
- [x] Visning av rå OCR-tekst for kontroll.
- [x] Sletting med bekreftelse; bilde, kvittering og prisobservasjoner fjernes.
- [x] Historikk med butikk-/datofilter og lasting av flere sider.
- [x] Produktsøk begrenset til brukerens data.
- [x] Konservativ normalisering av varenavn og størrelser; tvetydige fuzzy-treff slås ikke sammen.
- [x] Priser beregnes som linjetotal/antall (etter rabatt).
- [x] Billigste observasjon og siste pris per butikk beregnes separat.
- [x] Migrasjon 004 reparerer historiske prisobservasjoner.

## Verifikasjon og avgrensninger

Verifisert 2026-09-10:

- Backend: 37 tester bestått, inkludert OCR av alle tre eksempelbildene.
- Separat opt-in Compose-test: bestått med tre kvitteringer og reell OCR-worker.
- Python 3.12-container: 31 API-/parser-/migrasjonstester bestått.
- Android: 14 JVM-tester og 3 emulator-instrumenteringstester bestått (API 34).
- `assembleDebug`, `lintDebug` og `git diff --check`: bestått.
- PostgreSQL rapporterer Alembic-revisjon `004`; oppryddingsoppgaven ble kjørt gjennom Celery.
- Verktøykjeden rapporterer eksisterende deprecation-/avhengighetsadvarsler.

Automatiske tester dekker API, eierisolasjon, idempotens, sletting, migrasjoner,
parserformater, reelle OCR-bilder, sesjonsfornyelse, køfeil, gjennomgang og historikk.
En opt-in test kjører tre reelle kvitteringer gjennom Compose-stacken fra opplasting
til OCR, bekreftelse, produktsøk, prisvisning og sletting.

Android-instrumentering dekker Room/migrasjon og innlogging → historikk → produktsøk → utlogging mot lokal backend.
Fysisk kamerakvalitet på Samsung/Pixel og Google OAuth-verifikasjon krever separat
enhet-/kontokonfigurasjon.

Produksjonsdeploy 2026-09-10: commit `70256bf` pushet til `main`; API kjørte migrasjon
003 → 004. Worker er konfigurert med én OCR-prosess og innebygd Celery Beat.
Produksjonens `/health` rapporterer PostgreSQL og bildelagring `ok`; refresh- og
retry-endepunktene finnes i OpenAPI. Android er committet, men ikke publisert til Google Play.

Flere kvitteringer i ett bilde splittes ikke automatisk. Europris-parseren kan hente
venstre varelinjer fra det sammensatte eksempelbildet; bruk ett bilde per kvittering.
Ukjente butikkformater og usikker produktmatching krever brukerens gjennomgang.
30 dager er utløpsgrensen; faktisk sletting skjer ved neste scheduler-/WorkManager-kjøring.
