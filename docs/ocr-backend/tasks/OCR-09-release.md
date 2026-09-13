# OCR-09 — ende-til-ende-verifikasjon og kontrollert utrulling

## Selvstendig oppdrag

Prislapp har fått forslag til bedre OCR-tolking, særlig butikk og total. Denne oppgaven skal bevise at forbedringene faktisk når backendens reviewrespons og kan driftes uten å skade brukerdata. Grønne parserenhetstester alene er ikke tilstrekkelig.

Arbeid i `~/workprojects/prislapp`. Les hovedplan, kontrakt og handoffs fra **OCR-00–04, OCR-06 og OCR-07**. Inkluder OCR-05/08 bare når funksjonene faktisk er valgt/implementert. Dette er en verifikasjons-/releaseforberedelse, ikke automatisk tillatelse til deploy.

## Verifikasjon

1. Kjør opplasting av golden-bilder gjennom disponibel API/MinIO/Redis/worker/PostgreSQL-stack. Les samme HTTP-endepunkt som klienten bruker. Kontroller eksakt total, butikk, kilde, kvalitet og status, ikke bare 200 eller `READY_FOR_REVIEW`.
2. Kjør offentlig parserinngang på alle kjente kritiske feil: total på egen linje, tusenskille, mellomsum/rabatt, kontant/vekslepenger, MVA og butikkheader over flere linjer.
3. Verifiser null versus computed total gjennom faktisk v1/v2-respons og etter kladd/bekreftelse. Sikre at ny OCR ikke overskriver en brukerrettet total eller privat butikk.
4. Kjør samtidighets-/slettetester på PostgreSQL, kontrollert worker-krasj, timeout og tap av lease. Metadata må ikke bli hengende uten kvittering, og kontoavgrensning gjelder alle leseruter.
5. Verifiser automatisk utløp og sletting for nye artefakter. Ingen rå OCR/bilder/persondata i logger, standard benchmarkrapporter eller alarmer.
6. Kjør holdout én gang på den låste releasekandidaten. Rapportér eksakt treff, precision/coverage, sikre feil og manglende/uleselige tilfeller separat, samt latens/minne og datasettets størrelse.

## Releasekontroller

- Ny pipeline styres av versjonert konfigurasjon/feature flag. Migrasjon er additiv og rulles ut før writer som trenger den. Verifiser at gamle API-/workerprosesser tåler nye rader under rullering.
- Først lokal/staging. Eventuell shadow-kjøring skriver ikke til operative kvitteringsfelt, belaster ikke worker uten budsjett og følger samme retention. Ingen automatisk produksjonsshadow uten driftsgodkjenning.
- Pilotutrulling til avgrenset kohort etter manuell godkjenning. Observer andel manglende/ambivalent total/butikk, feltkorreksjoner der klienten sender dem, behandlingstid, feil og køalder. Korreksjon er et kvalitetsignal, ikke automatisk fasit for alle OCR-felt.
- Stopp ved nye kritiske falske sikre totalsummer, eierskapsbrudd, overskriving av kladd, vedvarende køvekst eller ressursbudsjettbrudd. Konkrete terskler/ansvarlig mottaker skal stå i runbook før aktivering.
- Rollback kan stoppe nye OCR-jobber eller deaktivere ny pipeline; skal ikke reversere brukerrettinger, slette rågrunnlag eller gjeninnføre kjent falsk sumfallback som «sikker» total. Planlegg trygg degraded-modus med null/usikkert felt.
- Gamle bilder reprosesseres ikke som del av release. Gamle bekreftede summer endres aldri fra et nytt OCR-resultat uten en egen revisjons-/brukerbeslutning.

## Kommandoer

Fra `backend/`:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/contracts/ -q
```

PostgreSQL-testene krever `PRISLAPP_POSTGRES_TEST_URL` mot en disponibel instans med tillatelsene beskrevet i repoets README. Bruk eksisterende lokale live-testoppsett og utvid det til de nye OCR-feltene. Ingen testkommando skal peke mot produksjon eller utføres med produksjonscredentials.

Benchmarkkommandoen tas fra OCR-00 sin overlevering; den finnes ikke nødvendigvis ved planens opprettelse. Registrer faktisk kommando og versjoner, ikke et planlagt resultat.

## Ferdigkriterier og overlevering

- Alle kritiske regresjoner er grønne, nødvendige PostgreSQL-/ende-til-ende-tester er kjørt, og reviewresponsen viser den målte forbedringen.
- Foreslåtte mål fra hovedplanen rapporteres ærlig med antall. Manglende holdout eller driftsmiljø er en blokkering for bred utrulling, ikke noe som skjules bak passerte enhetstester.
- Lever `docs/ocr-backend/handoffs/OCR-09.md` med releasekandidat/commit, test- og benchmarkresultater, skjema-/modellversjoner, åpne begrensninger, driftsrunbook, tilbakeføringsplan og eksplisitte manuelle godkjenninger som gjenstår.
- Ingen Androidendringer regnes som levert. Oppgi hvilke nye metadatafelter klienten senere bør vise, og hva eldre klient faktisk får av forbedring nå.
