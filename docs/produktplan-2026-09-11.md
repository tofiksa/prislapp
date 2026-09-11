# Prislapp: fra kvitteringsarkiv til nyttig handlehjelp

**Dato:** 11. september 2026  
**Status:** Forslag til produktretning og leveranseplan, ikke implementert funksjonalitet.  
**Detaljer:** [Spesifikasjoner og agentoppgaver](produktspesifikasjoner-2026-09-11.md)

## 1. Produktlederens konklusjon

Prislapp har et brukbart teknisk fundament: konto, kamera/galleri, brukerbundet opplastingskø, OCR, gjennomgang, kvitteringshistorikk, varesøk og egne historiske priser. Men appen er i dag først og fremst et kvitteringsarkiv. Handlelisten som skal gjøre dataene nyttige før og under neste handletur, mangler.

Den viktigste produktutfordringen er ikke antall funksjoner. Det er at **brukeren må gjøre arbeid i dag for å få en usikker gevinst senere**. Både registreringsarbeidet og usikkerheten må ned. Samtidig må appen være nyttig med bare én kvittering og uten nett i butikken.

Det ærlige produktløftet bør være:

> **Lag neste handleliste fra det du har kjøpt før, og se hvor du selv har betalt minst for samme vare.**

Ikke: «Vi finner dagens billigste dagligvarer.» Egne historiske kvitteringer forteller verken dagens pris, lagerstatus eller prisene i butikker brukeren ikke har registrert kjøp fra.

Ingen produktleder kan garantere at «folk flest» vil bruke en app med manuell kvitteringsregistrering. Før bred lansering bør vi bevise at en avgrenset gruppe faktisk får mer nytte enn arbeidet koster: personer som handler gjentakende varer i minst to butikker, og som ønsker å spare uten mye planlegging.

## 2. Overordnet liste over det som mangler

P0 betyr nødvendig for en trygg, nyttig ekstern pilot, ikke at alt skal bygges samtidig. P1 betyr nødvendig før bred utrulling. P2 er videreutvikling etter dokumentert nytte.

| Del | Gap i dagens produkt | Hva brukeren skal få | Prioritet |
|---|---|---|---|
| S01 | Høy startterskel og lite hjelp før historikken er stor | Forstå verdien før konto; første kvittering blir umiddelbart en gjenbrukbar vareliste | P0 |
| S02 | Registrering krever for mye kontroll; permanent feil kan blokkere køen | Ta/importer bilde, få konkret hjelp, og fortsett uten å miste kvitteringen | P0 |
| S03 | «Samme vare» er ikke sikkert nok; brukerinnsendte aliaser deles globalt | Private, korrigerbare vareidentiteter og riktig butikk/filial | P0 |
| S04 | Utydelig enhet, rabatt og prisalder | Etterprøvbar historisk pris med enhet, dato, vilkår og kilde | P0 |
| S05 | Tung OCR-gjennomgang og ingen retting etter bekreftelse | Kontroller primært usikre felt; rett feil også senere | P0 |
| S06 | Handlelister mangler helt | Lag liste raskt fra tidligere kjøp, bruk den uten nett og kryss av varer | P0 |
| S07 | Prisoppslag er løsrevet fra handleturen | Historisk billigste butikk per listevare, med tydelig forskjell mellom historisk minimum og siste observasjon | P0; helkurv P1 |
| S08 | Ingen tydelig gjenbrukssløyfe eller hjelp til å huske neste kvittering | Kopier tidligere handel og få valgfri, relevant påminnelse etter turen | Gjenbruk P0; påminnelser P1 |
| S09 | Kontogjenoppretting, kontosletting og brukerrettet personvern er ufullstendig | Trygg konto, forståelig lagring, eksport og sletting | P0 |
| S10 | For lite dokumentert kvalitet, måling og driftsberedskap | App som tåler dårlig nett, stor skrift, feil og oppgraderinger; et team som oppdager problemer | Grunnmur P0; bred matrise P1 |

### Hva vi bevisst ikke bygger først

- Tilbudsaggregator, scraping, andre brukeres priser eller sanntidspriser.
- Automatisk forslag om billigere alternativ vare som om den var identisk med ønsket vare.
- Ruteoptimalisering, lagerstatus eller løfter om at flere butikkbesøk lønner seg.
- Husholdningsdeling: dette krever et nytt, eksplisitt samtykke- og eierskapsregime.
- Poeng, streaks, sosiale funksjoner eller generisk KI-chat.
- Fullt regnskap, automatisk budsjett og kategorisering av alt forbruk.
- Betalingsmur foran grunnflyten før nytten er validert.
- Full gjestekonto med senere kontomigrering. En lokal, tydelig merket demonstrasjon er tilstrekkelig først.

## 3. Den sammenhengende brukerreisen

1. **Forstå:** «Fotografer kvitteringen én gang. Bruk varene i neste handleliste.» En demonstrasjon forklarer begrensningene.
2. **Registrer:** Kamera eller galleri. Brukeren kan forlate skjermen; køen fortsetter når nett er tilgjengelig.
3. **Kontroller:** Appen peker ut usikre priser, datoer og koblinger. Brukeren bekrefter; bildet kan forstørres.
4. **Få første verdi:** «12 varer klare til neste handleliste.» Ingen krav om kvitteringer fra flere butikker for å bruke listen.
5. **Planlegg:** Velg «Kjøp igjen», søk eller kopier en tidligere handel. Velg mengde.
6. **Vurder pris:** «Laveste registrerte pris: 24,90 kr hos Rema 1000 [filial], 8. september.» Siste kjente pris vises separat.
7. **Handle:** Listen åpner raskt uten nett. Avkryssing er lokal og mister ikke tilstand ved appstopp.
8. **Oppdater:** Avslutt turen. Frivillig oppfordring til å ta bilde av kvitteringen; ingen automatisk innkjøpsregistrering fra avkryssing.

### Nødvendige tilstander, ikke bare normalflyten

- **Ingen kvitteringer:** Demonstrasjon og registrering; ingen falsk prisinformasjon.
- **Én butikk:** Nyttig handleliste og «Registrert i én butikk — ingen butikksammenligning ennå».
- **Vare ikke kjøpt før:** Fritekstlinje uten pris; den må ikke hindre resten av handelen.
- **Gammel pris:** Historikken beholdes, men merkes som gammel. Ingen skjult aldersgrense som fjerner den eneste nyttige informasjonen.
- **Ukjent dato/enhet/matching:** Ingen umerket anbefaling. Forklar hva som må kontrolleres.
- **Delvis prisdekning:** Vis hvilke varer som mangler; ukjent er aldri 0 kr.
- **Offline:** Listen fungerer. Prisdata viser når de sist ble hentet, separat fra kjøpsdatoen.

## 4. Hva kodegjennomgangen faktisk viser

Undersøkelsen omfattet Android-kilde, backend, tester, migrasjoner og dokumentasjon. Appen er ikke kjørt på enhet, og det er ikke kjørt nye tester eller kontrollert produksjonsoppsett som del av analysen. Kodefunn er ikke det samme som en full sikkerhetsrevisjon. Filreferansene nedenfor er fra kildegrunnlaget undersøkt denne datoen.

| Funn | Kilde |
|---|---|
| Navigasjonen har Hjem, Historikk og Søk, men ingen handleliste | `android/app/src/main/java/no/prislapp/ui/navigation/Routes.kt:3–18`, `PrislappNavHost.kt:48–203` |
| Room lagrer opplastingskø, ikke handleliste/prishistorikk | `android/app/src/main/java/no/prislapp/data/local/PrislappDatabase.kt:8–14` |
| Alle opplastingsfeil retryes; løkken stopper på første feil | `android/app/src/main/java/no/prislapp/worker/ReceiptUploadWorker.kt:27–38` |
| Aldersopprydding omfatter også lokale køelementer som ikke er ferdig opplastet | `android/app/src/main/java/no/prislapp/data/repository/ReceiptRepository.kt:188–196` |
| Kvitteringsbildet vises beskåret, uten zoom; bekreftede kvitteringer er read-only | `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptScreens.kt:342–353`, `ReceiptViewModels.kt:164–211` |
| Produktmatching søker i globale aliaser; prisene er derimot brukeravgrenset | `backend/app/services/product_service.py:24–103`, `product_price_service.py:38–73` |
| Pris beregnes fra linjesum/mengde; oppgitt enhetspris styrer ikke observasjonen | `backend/app/services/receipt_service.py:207–237` |
| Ukjent kjøpsdato erstattes med bekreftelsestidspunkt | `backend/app/services/receipt_service.py:197–208` |
| «Billigst» er minimum over historikk, ikke dagens pris | `backend/app/services/product_price_service.py:65–111` |
| Separate rabattlinjer ignoreres av generisk parser | `backend/app/parsers/generic.py:10–12,32–45` |
| Kontoopprettelse finnes, men ikke kontosletting eller eksport | `backend/app/routers/auth.py`, `android/app/src/main/java/no/prislapp/data/remote/PrislappApi.kt:29–85` |
| Standard JWT-hemmelighet er konfigurert som fallback; faktisk produksjonsverdi er ikke undersøkt | `backend/app/config.py:7–21` |

## 5. Hvordan vi vet at dette blir et produkt, ikke bare flere funksjoner

### Før utviklingen blir stor

Gjennomfør først 6–8 observerte brukerøkter med dagens app og en klikkbar handlelisteprototype. Rekrutter både personer med høy og lav teknisk selvtillit. Bruk egne kvitteringer bare etter informert samtykke; ellers anonymiserte testkvitteringer. Undersøk spesielt:

- Forstår de forskjellen på historisk og aktuell pris?
- Klarer de å oppdage feil varevariant og feil pris?
- Hvor mye kvitteringskontroll oppleves som rimelig?
- Velger de faktisk en annen butikk, eller ønsker de først og fremst en god gjenbruksliste?
- Oppleves én butikk til som bryet verdt? Ikke anta at kroner alene avgjør.

### Hypoteser og foreslåtte pilotmål

Dette er **produktmål som må kalibreres**, ikke observerte resultater eller Googles formelle kvalitetsgrenser.

| Måling | Definisjon | Foreløpig mål |
|---|---|---|
| Aktivering | Andel nye reelle pilotbrukere som bekrefter en kvittering og lager en liste med minst 3 historiske varer innen 7 dager | Minst 60 % |
| Gjennomgangsfriksjon | Aktiv tid fra review åpnes til bekreftelse for en lesbar kvittering med 10–20 linjer; OCR-venting rapporteres separat | Median under 60 sekunder |
| Listefriksjon | Observerte brukere lager liste med 10 tidligere varer uten hjelp | Minst 80 % på under 90 sekunder |
| Prisforståelse | Brukeren kan forklare at «lavest registrert» ikke garanterer dagens pris | Minst 90 % i brukertest |
| Gjentatt nytte | Aktiverte brukere som bruker en liste i minst 2 ulike uker i de første 4 ukene | Minst 40 % |
| Tillit | Kjente kritiske feil som gir sammenligning av feil enhet/variant eller andre brukeres data i utgitt versjon | 0 åpne feil |

Primær produktmåling: **ukentlig antall brukere som bruker en historikkbasert handleliste**. Vis både antall og andel av aktiverte brukere; segmenter etter historikkstørrelse og antall butikker. Ren opplastingsmengde belønner brukerarbeid, ikke nytte.

Ikke mål «kroner spart» som en sikker fasit. En alternativ handlekurv ble ikke kjøpt, og dagens alternative butikkpris er ukjent. Eventuell senere differansevisning skal hete «historisk prisforskjell», med eksplisitt beregningsgrunnlag.

## 6. Leveranserekkefølge og beslutningsporter

### A. Sikre fundamentet

- Kontraktbeslutninger, sikker konfigurasjon, kontoisolasjon og CI.
- Robust opplastingskø og grunnleggende driftsgjenoppretting.
- Privat produktidentitet, enhet/dato/proveniens og korrigerbare observasjoner.
- Kontosletting og personvern før ekstern pilot.

**Port:** Ingen kjente P0-datafeil, gjenopprettingstest bestått, migrering verifisert på PostgreSQL. Android-skjelett/prototype kan utvikles parallelt mot avtalte kontrakter.

### B. Lever én komplett vertikal brukerreise

- Registrer én kvittering → bekreft → kjøp igjen → handleliste → historisk pris per vare → bruk uten nett → registrer neste kvittering.
- Enkel onboarding, alle tom-/feiltilstander og instrumentering.

**Port:** Ende-til-ende-tester og observerte brukerøkter består. Ekstern pilot med 20–30 brukere i minst fire uker; rapporter usikkerhet ved små utvalg.

### C. Reduser friksjon og utvid kontrollert

- Bedre bildeverktøy, flere dokumenterte kvitteringsformater, valgfri påminnelse.
- Én-butikkestimat med tydelig prisdekning, uten falsk «billigste kurv».
- Utvidet enhets-/tilgjengelighetstesting og trinnvis Play-utrulling.

**Port:** Brukerne kommer tilbake, prisinformasjonen forstås og feilbelastningen er håndterbar. Hvis ikke: forbedre registreringsarbeid og gjenbruksverdi før nye funksjoner.

## 7. Delegeringsregler

- Oppgaver og kontrakter står i [spesifikasjonsdokumentet](produktspesifikasjoner-2026-09-11.md). Hver oppgave-ID kan gis til én kodeagent.
- Ingen agent skal tolke «billigst» annerledes eller velge egen penge-/enhetsmodell.
- Avtal API og migrasjonsstrategi før parallelle Android/backend-implementasjoner.
- Lag tester som feiler før implementasjon; rapporter faktiske testkommandoer og resultater.
- Agenter endrer ikke produksjon, secrets, Play Console eller deploy uten separat godkjenning.
- Eksterne beslutninger som personvernerklæring, OAuth-konfigurasjon og Play-skjema har en navngitt menneskelig eier; de regnes ikke som løst av kode alene.

## 8. Play-kvalitet og kildegrunnlag

Google Play krever for apper med konto-opprettelse en tilgjengelig vei for å be om kontosletting i appen og en fungerende nettressurs for samme formål. Dette er noe annet enn å bare slette én kvittering. Kilden ble kontrollert 11. september 2026:

- [Google Play: krav til kontosletting](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en).
- [Android Core App Quality](https://developer.android.com/docs/quality-guidelines/core-app-quality) er relevant utgivelsessjekkliste, men siden lot seg ikke hente i denne undersøkelsen. Gjeldende krav til mål-API, skjermstøtte og Play-policy må kontrolleres på utgivelsestidspunktet.

Øvrige tall og produktprioriteringer her er egne anbefalinger. Dokumentet representerer ikke en offisiell Google-vurdering eller godkjenning for Play Store.
