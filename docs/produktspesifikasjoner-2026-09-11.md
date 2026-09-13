# Prislapp: delegerbare produktspesifikasjoner

**Dato:** 11. september 2026  
**Status:** Foreslått implementasjonsgrunnlag. Ingen funksjoner er implementert gjennom dette dokumentet.  
**Les først:** [Produktretning, gap og prioritering](produktplan-2026-09-11.md).

## 0. Felles kontrakter og beslutninger

Disse reglene gjelder alle oppgavene. Teknisk leder og produktansvarlig godkjenner dem i `C00` før kodeagentene starter overlappende implementasjoner. Dette er foreslåtte kontrakter; eksisterende API-er skal ikke brytes uten en eksplisitt overgang.

### 0.1 Produktgrenser

1. Priser kommer utelukkende fra den innloggede brukerens egne, bekreftede kvitteringer.
2. En avkrysset handleliste er ikke en kvittering og oppretter aldri prisobservasjoner.
3. Samme vare betyr samme merke, variant, pakningsinnhold og pakningsantall. Brukerbekreftelse kan avklare manglende identitetsopplysninger, men kan ikke gjøre motstridende pakningsdata sammenlignbare. Alternative varer er en eventuell separat relasjon, aldri felles pakningsminimum. Fuzzy navnelikhet alene er ikke bevis.
4. Ukjent produktidentitet, enhet, dato eller rabattbehandling skal representeres som ukjent. Aldri fyll inn «sannsynlige» verdier som om de var bekreftet.
5. Andre størrelser kan senere sammenlignes på kr/kg eller kr/l, men skal ikke automatisk erstatte varen i en liste.
6. Norge/NOK er første støttede marked. Utenlandsk valuta kan arkiveres, men utelukkes fra sammenligning inntil valuta faktisk støttes. Ingen valutakonvertering i første versjon.

### 0.2 Identitet, eierskap og revisjoner

- `user_id` utledes fra autentisering, aldri fra klientinput som autorisasjonsgrunnlag.
- Alle private ressurser bruker UUID, eierfilter og 404 ved forsøk på å bruke en annen eiers ID. Også referanser i request body kontrolleres.
- Privat `UserProduct` erstatter global, brukerinnsendt produktidentitet i nye flyter. En fremtidig kuratert global katalog er et separat, valgfritt lag.
- Kvitteringslinjer har stabile ID-er, rekkefølge og kobling til kilde/revisjon. Retting er en revisjon, ikke usporbar overskriving.
- Endringsbare ressurser har `version`. Mutasjoner har klientgenerert `mutation_id`; nye ressurser kan ha klientgenerert UUID for offlinebruk.
- Samme bruker + operasjon + mutasjons-ID + samme payload returnerer samme resultat. Samme nøkkel med annet innhold gir 409. Versjonskonflikt gir 409 med gjeldende versjon, ikke stille overskriving.

### 0.3 Penger, mengder og prisgrunnlag

- Penge- og mengdeverdier sendes som desimalstrenger i JSON. Backend bruker `Decimal`, Android `BigDecimal`; aldri flyttallsregning for penger.
- Betalte NOK-linjebeløp har to desimaler. Mengder har inntil tre desimaler. Lagre nok presisjon for beregnet sammenligningspris, foreslått seks desimaler, og rund først ved visning/sluttbeløp med eksplisitt `ROUND_HALF_UP`.
- `quantity_unit`: `each`, `kg`, `g`, `l`, `ml`, `unknown`. For pakningsvarer er ønsket listemengde antall pakninger; pakningsinnhold lagres separat. Normaliser g til kg og ml til l før sammenligning, ikke stk til kg uten kjent pakningsinnhold.
- `line_type`: `product`, `deposit`, `fee`, `discount`, `return`, `unknown`.
- `net_line_total` er faktisk beløp tilordnet varelinjen etter dokumentert rabatt. `printed_unit_price` er et separat lest felt, ikke en konkurrerende fasit.
- `price_basis`: `per_package`, `per_kg`, `per_litre`, `unknown`. Pakningspris og kr/kg er separate verdier med eksplisitt etikett.
- Linjer med uavklart rabattfordeling/retur/enhet kan lagres, men gir ikke automatisk rangerbar pris.
- Vilkår: `none`, `member`, `multi_buy`, `coupon`, `unknown`. Gratisvarer beholdes som kjøpshistorikk, men er ikke standardgrunnlag for neste kjøpsråd.

### 0.4 Dato, prisalder og proveniens

- Skill `purchase_date`, valgfri `purchase_time`, `date_precision` (`date`, `datetime`, `unknown`), `date_source` (`ocr`, `user`, `unknown`), `uploaded_at` og `confirmed_at`.
- Ikke bruk opplasting/bekreftelse som skjult kjøpsdato. Bevar lest klokkeslett hvis brukeren bare bekrefter datoen. Dato uten klokkeslett skal ikke oppgraderes til et sikkert tidspunkt ved midnatt.
- Observasjoner inkluderer ID, kvitterings-ID, linje-ID, revisjon, bruker, produkt, butikk, enhet, valuta, kjøpsdato, vilkår og kvalitetsstatus.
- Foreslåtte aldersetiketter: 0–30 dager «registrert nylig», 31–90 dager «eldre observasjon», over 90 dager «gammel observasjon». Alle viser faktisk dato/alder og «Dagens pris kan være annerledes». Grensene er justerbare produktvalg, ikke bevis på at prisen fortsatt gjelder.
- «Lavest registrert» bruker hele kvalifisert historikk. «Siste registrerte» er et annet felt. Ved lik pris vises alle delte førsteplasser. Ved flere observasjoner samme dag uten sikkert klokkeslett vises datousikkerhet/prisspenn; ikke kall laveste pris den siste.

### 0.5 API, cache og kompatibilitet

- Behold eksisterende ruter under overgang. Nye kontrakter beskrives i OpenAPI før klientimplementasjon; nedenfor brukes `/v2` for endrede domener.
- Feilformat: `code`, trygg `message`, `field_errors`, `retryable`, `request_id`. Ingen OCR-tekst, tokens eller intern stacktrace i feilmeldinger/logg.
- Paginering bruker cursor og stabil sekundærsortering på ID. Standard 50, maks 100. Produkter kan listes uten søketekst.
- Sammenligningsrespons inkluderer `list_version`, `price_data_version`, `calculated_at` og `policy_version`. Eldre svar skal ikke erstatte nyere UI-tilstand.
- Kontoavgrenset lokal database/cache/outbox. Ingen data eller ventende mutasjoner sendes med en annen kontos token. Ved logout skjules data straks, workers stoppes for kontoen og bilde-/token-cache ryddes. Uopplastede kvitteringer utløser tydelig valg før lokal sletting.
- Uthenting av cached priser er ikke et nytt kjøp: vis både «priser hentet» og «kjøpt» med hver sin dato.
- Sync returnerer også kontoens monotont økende `price_data_version` og endrede/erstattede private produkt-ID-er. Retting, sletting og merge øker versjonen transaksjonelt. Ved endret versjon markeres pris-cache foreldet og relevante produkt-/prisdata hentes på nytt. Fullt snapshot gjenoppretter også produktreferanser ved utløpt cursor.
- Batchprising av en serverliste skjer først etter at lokale endringer er synket og serverens `list_version` er kjent. Inntil da beholdes merket cache eller «Pris oppdateres etter synkronisering»; gammel sum må ikke knyttes til nytt vareutvalg. Offline retting på en annen enhet kan ikke oppdages før kontakt gjenopprettes; ingen umiddelbar cachegaranti loves i flymodus.

### C00 — kontraktoppgaven

**Eier:** Backend-/arkitekturagent med Android-review.  
**Leveranse:** Datadiagram, OpenAPI-skjemaer med eksempelresponser, avrundingsregler, feilkontrakt, offline-konfliktprotokoll, migrasjonsplan og ADR for privat produktidentitet.  
**Akseptanse:** Android og backend kan bygge fra samme fixtures; ukjent/delvis/lik pris, rabatt, kg-vare og gammelt kjøp har entydige eksempler. Gjeldende klientversjon har definert overgang. Ikke sett i gang destruktiv migrering.

---

## S01. Første verdi og navigasjon

**Problem:** Konto og registreringsarbeid kommer før verdien. En tom søkeskjerm forteller ikke hvordan appen hjelper neste handletur.  
**Mål:** Første bekreftede kvittering skal gi gjenbrukbare varer, selv uten prissammenligning mellom butikker.

### Brukeropplevelse

1. Kort velkomst med produktløftet og to valg: «Se eksempel» og «Registrer kvittering».
2. Eksemplet bruker kun lokal, tydelig merket demodata. Ingen konto, nett eller analytics kreves for å forstå flyten. Demodata blandes aldri med egne priser.
3. Ved første reelle opplasting kreves konto og kort forklaring om lagring av bilder og kjøpsdata. Kameraetterspørsel kommer først når brukeren velger kamera.
4. Etter bekreftelse: «N varer klare til neste handel» → velg varer → «Lag handleliste».
5. Innlogget hovednavigasjon: **Handleliste / Varer / Kvitteringer**. Konto/innstillinger tilgjengelig fra toppnivå. Kamera/import tilgjengelig fra Kvitteringer og etter avsluttet handel.
6. Bevar eksisterende historikk- og filterfunksjoner under Kvitteringer. Tilbake går til faktisk forrige skjerm; ikke alltid Hjem.
7. Initial auth-tilstand er «avklares», ikke utlogget, for å unngå feil skjermblink ved kaldstart.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S01-A | Android: velkomst, demoflyt, kontekstuell tillatelse og lokale førstegangsvalg | C00 | Demo fungerer i flymodus; avslutning fjerner demoens tilstand; realdata får aldri demoens priser |
| S01-B | Android: ny navigasjon og første-kvittering-CTA | S06-A/B, S03-C | Etter første bekreftelse kan bruker lage liste med 3 varer uten manuell gjeninntasting; historikk og back-stack fungerer |
| S01-C | Android/backend: ærlige tomtilstander for null varer, én butikk og manglende dekning | S04-B, S07-A | Ingen tilstand hevder sammenligning når bare én butikk er kjent; feil ved uthenting er ikke «ingen data» |

**Test:** Compose-navigasjonstest gjennom demo → innlogging → kvittering → liste, cold start med lagret sesjon, avvist tillatelse og gjenåpning etter prosessdød. Brukertest av prisforståelse, ikke bare klikkbarhet.  
**Kodeområder:** `ui/navigation`, `ui/auth`, `ui/home`, `ui/history`, `ui/product`, `res/values/strings.xml`.

---

## S02. Enkel og tapsfri kvitteringsregistrering

**Problem:** Kvitteringen er brukerens innsats og appens eneste priskilde. En tapt opplasting eller uforståelig OCR-feil ødelegger tilliten.  
**Mål:** Registrering skal være mulig med dårlig nett, avvist kamera og midlertidig serverfeil.

### Funksjonelle krav

- Behold CameraX, Photo Picker, Room og WorkManager. Ikke bygg disse grunnfunksjonene på nytt.
- Etter kamera: forhåndsvisning med «Bruk bilde» / «Ta på nytt», zoom og enkel rotasjon. Beskjæring og veiledning for lange kvitteringer er P1. Flerbilde-sammensetting og PDF er ikke med i første leveranse.
- Kontroller faktisk filtype og dekoding. Konverter ved behov og send riktig MIME-type. Backend kontrollerer også dimensjoner/dekodet størrelse for å begrense ressursbruk.
- Ingen stille nedskalering som gjør teksten uleselig. Kvitteringsfixtures avgjør komprimeringsnivå; teknisk grense og feilmelding dokumenteres sammen.
- Lokal kvittering lagres før appen viser «lagret». Vis thumbnail, opptakstid og status.
- Tilstander: `queued_offline`, `uploading`, `processing`, `ready_for_review`, `needs_action`, `failed_permanent`. Serverfeil og lokal opplastingsfeil holdes adskilt.
- Retrybare feil: nettbrudd, timeout, 429 etter `Retry-After`, 5xx. Feil innlogging pauser køen for reautentisering. Ugyldig/stor fil og borte lokal fil er permanente feil; de blokkerer ikke senere elementer.
- Brukeren kan fjerne et lokalt element med bekreftelse. Å stoppe venting på status skal ikke starte OCR på nytt. OCR-retry tilbys bare når serverstatus og bildet tillater det.
- Aldersopprydding skal ikke stille slette uopplastede kvitteringer. De beholdes til vellykket opplasting eller eksplisitt valg; synlig varsel ved lagringspress og i innstillinger. Ukjent-eier-arv håndteres særskilt uten å vise innhold til ny konto.
- Serverarkivet kan filtreres på «Trenger gjennomgang» og er paginert. En gammel ubekreftet kvittering skal ikke bli utilgjengelig fordi den ikke er blant de 20 nyeste.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S02-A | Android: køtilstander, retryklassifisering, lokal fjerning og trygg retention | C00 | En permanent feil først i køen hindrer ikke to gyldige bilder bak; flymodus/prosessdød mister ingen kvittering; gammel uopplastet fil slettes ikke automatisk |
| S02-B | Android: bildeforhåndsvisning, zoom/rotasjon, formathåndtering | C00 | JPEG/PNG og testet støttet galleriinput får korrekt visning/opplasting; avvist format gir konkret tiltak; galleri fungerer uten kamera |
| S02-C | Backend: filgrenser, formatmetadata, idempotens med payload-hash og feilkontrakt | C00, S10-B | Lik nøkkel/lik fil gir én kvittering; lik nøkkel/ulik fil gir 409; farlige dimensjoner avvises før OCR |
| S02-D | Android/backend: paginert behandlingsinnboks og deduplisering lokal/server | S02-A/C | Kvittering nummer 51 i review er tilgjengelig; samme opplasting vises bare én gang; polling-retry kaller ikke OCR-retry |

**Test:** Nettbrudd før/etter servercommit, 413, 429, 500, refresh-feil, kontoendring under upload, bortkommet fil, 31 dager i kø, serverfeil og flere køelementer.  
**Kodeområder:** `ui/camera`, `data/repository/ReceiptRepository.kt`, `worker/ReceiptUploadWorker.kt`, lokale kømodeller, `backend/app/routers/receipts.py`, `services/storage_service.py`.

---

## S03. Private vareidentiteter og riktige butikker

**Problem:** Automatisk global matching kan både samle forskjellige varer og splitte samme vare. Det gjør prisråd feil, selv om OCR-prisen er riktig.  
**Mål:** Brukeren skal forstå og kunne rette «samme vare», uten å påvirke andre brukere.

### Datamodell og regler

- `UserProduct`: eier, visningsnavn, valgfritt merke/variant, pakningsmengde/enhet, pakningsantall, identitetsstatus, versjon og tidsstempler.
- `UserProductAlias`: eier, produkt, normalisert tekst, valgfri butikk-/kjedekontekst, kilde og matchmetode. Privat kobling er fasit; globale brukerinnsendte aliaser skal ikke brukes som autoritativ match.
- Behold original varetekst. Foreslå match til tidligere privat bekreftet alias i samme kontekst. Fuzzy matching er et forslag, ikke automatisk prisgrunnlag på tvers av butikker.
- «YOGHURT» uten variant/pakningsstørrelse skal kunne stå uavklart. UI gir «Er dette samme vare som …?» med relevante egenskaper og tidligere kvitteringskilde.
- Brukeren kan velge tidligere vare, opprette ny, endre eget navn, slå sammen egne dubletter og flytte utvalgte kvitteringslinjer til en annen/ny vare. Flytting erstatter behovet for en kompleks generell split-editor i MVP.
- Sammenslåing viser berørte historikklinjer og handlelistekoblinger før bekreftelse. Rettingen påvirker bare eget datasett og øker `price_data_version`.
- Butikk: kjede, filialnavn, valgfri adresse og identitetsnivå `branch`, `chain_only`, `unknown`. Normalisert navn alene er ikke bevis på samme filial.
- Ubekreftet butikktekst og aliaser er private. Et eventuelt delt, kuratert butikkregister mottar ikke automatisk brukerens OCR-tekst.
- «Rema 1000, ukjent filial» skal vises som dette; ikke slå sammen alle kjedens filialer eller presentere en kjedepris som en bestemt butikks pris.
- Kvalifiseringsmatrise: `branch` kan inngå i butikkminimum, antall sammenlignbare butikker og butikkestimat. `chain_only` og `unknown` vises som egne historiske kjøp med pris, men får ikke vinnermerking, telles ikke som sammenlignbare filialer og inngår ikke i butikkestimat før brukeren avklarer filial. Kjent og ukjent filial i samme kjede er aldri to dokumenterte butikker.
- Merge med motstridende variant-/pakningsdata avvises med feltfeil. Brukeren må først korrigere feil metadata fra kildegrunnlaget eller beholde varene atskilt; generell «jeg bekrefter»-handling omgår ikke regelen.

### API-utvidelser

- `GET /v2/me/products?q=&sort=recent|frequent|name&cursor=` med navn, pakning, siste kjøpsdato, antall kjøp og identitetsstatus.
- `PATCH /v2/me/products/{id}` med versjon.
- `POST /v2/me/products/{id}/merge` med kilde-/mål-ID, versjoner og mutasjons-ID.
- Produktvalg på kvitteringslinje gjennom revisjons-API i S05.
- `GET /v2/me/stores` og privat butikkretting med tydelig filialstatus.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S03-A | Backend: privat produkt-/butikkmodell og additiv migrering | C00, S10-A | A sine navn/aliaser påvirker ikke B; backfill bruker egne kvitteringslinjer, ikke ukjent global aliasopprinnelse; uavklart status bevares |
| S03-B | Backend: privat matching, merge og flytting med prisgjenberegning | S03-A, S04-A, S05-A | 200 g/400 g, ulike fettprosenter og kg/stk blandes ikke; merge er atomisk og idempotent; flytting oppdaterer riktig eiers priser |
| S03-C | Android: «Mine varer», søk/kjøp igjen, matchforslag og butikkvalg | S03-A og låst API | Bruker kan rette ett feiltreff uten å slette kvitteringen; ny vare kan opprettes uten tvungen gjetning; søk har stabil paginering |
| S03-D | Backend/QA: migreringsrevisjon og kompatibilitetslag | S03-A/B | Hver gammel bruker-/produktkobling har dokumentert ny ID; ingen kopiering av andres tekst; ingen handlelistelenker brytes |

**Migrering:** Lag private produkter per eksisterende `(user_id, product_id)`, men merk arvet matching som uavklart der det ikke finnes sikkert eget grunnlag. Behold originaltekst og mappingtabell. Eksisterende feilaktige globale sammenslåinger kan ikke løses sikkert maskinelt. Prisråd på slike data må be om avklaring; ikke slett historikken.  
**Test:** To brukere med samme rånavn, samme bruker i ulike butikker, samtidige produktopprettelser, norsk tekst, aliasduplikater, feilmerge og etterfølgende flytting.  
**Kodeområder:** `backend/app/models/product.py`, `models/store.py`, `services/product_service.py`, `services/receipt_service.py`, Android `ui/product` og DTO-er.

---

## S04. Pålitelig prisgrunnlag

**Problem:** Laveste tall er ikke nødvendigvis laveste sammenlignbare pris. Enhetsfeil, gamle tilbud og ukjent dato kan gi misvisende råd.  
**Mål:** Hvert presenterte minimum skal kunne forklares fra brukerens kvittering.

### Beregningsregler

1. Bare gjeldende, bekreftede kvitteringsrevisjoner med kvalifisert produktidentitet brukes.
2. Krev NOK, kjent prisgrunnlag, positiv mengde og avklart nettolinjesum. Dato må være kjent for datert rangering; ukjent dato vises separat uten tidsbasert påstand.
3. For pakningsvarer: nettolinjesum / antall pakninger. For vekt-/volumvarer: nettolinjesum / normalisert kjøpt kg/l.
4. Beregn standardisert kr/kg eller kr/l bare ved kjent pakningsinnhold. Ikke bland denne verdien med pakningsprisen i minimumet.
5. Pant/gebyr/retur er ikke vareminimum. De vises separat i kvitteringsavstemming. Ukjent kurvrabatt fordeles ikke forholdsmessig uten dokumentert regel og brukeravklaring.
6. Standard prisråd utelater kjente medlems-, kupong-, gratis- og flerkjøpsbetingelser. «Inkluder kjøp med vilkår» er et eksplisitt filter og viser vilkårene; ukjent rabattbehandling er fortsatt ikke kvalifisert.
7. Vis både laveste kvalifiserte observasjon over hele historikken og siste kvalifiserte observasjon per butikk. Vilkårspriser kan fortsatt sees i kjøpshistorikken.
8. Historisk minimum vises også når gammelt, med alder. Ingen påstand om aktuell pris eller faktisk besparelse.
9. Ved retting/sletting/merge beregnes berørte resultater på nytt og cache ugyldiggjøres.

### Foreslått prisrespons

`GET /v2/me/products/{id}/prices?include_conditional=false&cursor=` returnerer:

- Produkt, pakning, valuta og prisgrunnlag.
- `historical_lowest`: beløp, alle delte førsteplasser, kjøpsdato, butikkidentitet, kilde, vilkår og advarsler; null hvis ingen kvalifiserte observasjoner.
- `latest_by_store`: siste sikre observasjon eller tydelig samme-dag-usikkerhet.
- `eligible_store_count`, `excluded_observation_count` og årsaker som `unknown_unit`, `unresolved_identity`, `unknown_discount`, `unknown_date`.
- Paginert historikk med kildehenvisninger også for ekskluderte kjøp. Oppsummeringer beregnes over hele grunnlaget, ikke bare returnert side.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S04-A | Backend: enheter, linjetyper, dato-presisjon, vilkår og eksakt beregning | C00, S03-A | Delt enhets-/pengefixture består; ukjent dato blir aldri dagens kjøp; gamle data får ikke gjettede enheter |
| S04-B | Backend: prisoppslag, kvalifisering, proveniens og cacheversjon | S04-A | Et billigere, uavklart treff blir ikke vinner; alle like minimum vises; samme-dag-usikkerhet skjules ikke |
| S04-C | Android: prisdetalj med enhet, alder, vilkårsfilter og kilde | S04-B | «Lavest registrert» og «Siste registrerte» er separate; kilden kan åpnes selv når bildet har utløpt |
| S04-D | Backend/QA: kontrollert backfill og sammenligning ny/gammel algoritme | S04-A/B, S03-D | Endringer rapporteres per årsak; ingen stille overskriving av rågrunnlag; avrunding er lik i Python, SQL og Android |

### Obligatoriske fixtures

- To pakker til sammen 40,00 gir 20,00 per pakke; 0,385 kg til 31,90 sammenlignes i kr/kg, aldri kr/stk.
- En 400 g-pakke og en 200 g-pakke får ikke samme pakningsminimum, selv med likt produktnavn.
- Vare 40,00 + separat rabatt −10,00 gir 30,00 når sikkert tilordnet; ellers «må avklares» og ingen standardrangering.
- 2,01 / 2 gir eksakt 1,005 internt og 1,01 ved visning med avtalt avrunding.
- Gammel pris 19,90 og nyere 29,90 i samme butikk vises som to forskjellige fakta.
- Udatert kvittering importert i dag blir ikke en fersk prisobservasjon.
- En produktretting fra 2,50 til 25,00 fjerner det feilaktige minimumet også fra cached lister.

**Kodeområder:** `schemas/receipt.py`, `models/receipt_item.py`, `models/product.py`, `services/receipt_service.py`, `services/product_price_service.py`, nye Alembic-migrasjoner og Android pris-DTO/-skjerm.

---

## S05. Effektiv gjennomgang og retting

**Problem:** Brukeren må kontrollere mange felt mot et beskåret bilde, og feil blir låst etter bekreftelse.  
**Mål:** Kontroller lett, lagre trygt og korriger uten å registrere hele kvitteringen på nytt.

### Brukeropplevelse og regler

- Review har eksplisitte tilstander: lasting, lastingsfeil med retry, redigerbar kladd, lagrer, bekreftet og revisjonskonflikt. Lastingsfeil skal aldri vise et tomt bekreftbart skjema.
- Del skjermen i «Må kontrolleres» og øvrige linjer. OCR-konfidens vises ikke som sikker sannhet; bruk strukturelle advarsler og kalibrerte kvalitetssignaler.
- Fullskjermbilde med zoom/pan, og kildeområde når OCR-boks finnes. Bildeutløp forklares; feltene kan fortsatt rettes fra brukerens kunnskap.
- Feltvis validering, norsk desimaltastatur og tilgjengelig fokus på første feil. Ingen tre trange tallfelt som blir ubrukelige ved stor skrift.
- Avstem sum av netto varelinjer, pant, gebyrer, returer og rabattjusteringer mot trykt total. Beregnet fallback-total merkes og teller ikke som uavhengig avstemming.
- Avvik større enn 0,01 kr krever forklaring eller retting. Kvitteringen kan lagres med avvik; prisråd begrenses til eksplisitt bekreftede linjer med avklart prisgrunnlag. Hvis avviket kan skyldes ufordelt rabatt, hold berørte priser ute.
- Ukjent butikk, dato eller identitet er ikke datatap: lagre kvitteringen, forklar hvorfor den ikke gir sammenligningspris ennå.
- Kladd lagres lokalt per konto ved endring og overlever prosessdød. Nettkopi av kladd kan lagres med versjon; bekreftelse krever nett og er idempotent.
- «Rediger» på bekreftet kvittering oppretter en ny revisjon. Serveren oppdaterer linjer/observasjoner atomisk. Sletting får bekreftelse og opplyser om påvirkning på prishistorikken.
- Ved 409 beholdes lokal kladd. Brukeren kan se serverversjonen og velge retting på nytt, ikke miste alt eller overskrive blindt.

### API og oppgaver

Nye ruter: `PUT /v2/receipts/{id}/draft`, `POST /v2/receipts/{id}/confirm`, `POST /v2/receipts/{id}/revisions`. Requests bruker stabile linje-ID-er, `expected_version` og `mutation_id`. Siste to returnerer gjeldende kvitteringsrevisjon og ny prisdataversjon.

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S05-A | Backend: revisjoner, atomisk confirm/retting og avstemming | S03-A, S04-A | Dobbelt confirm gir én revisjon; retry etter tapt svar returnerer samme resultat; gammel revisjon publiserer ikke priser |
| S05-B | Backend: OCR-/parserproveniens og strukturelle advarsler | C00, S04-A | Parserfeil bevarer lovlig rågrunnlag; null varer merkes; total lest vs beregnet er forskjellig; versjon lagres |
| S05-C | Android: review, lokal kladd, zoom, feltfeil og konfliktvisning | S05-A/B, S03-C | Prosessdød bevarer endringer; OCR-tid bevares ved uendret dato; bekreftet pris kan rettes og leses på nytt |
| S05-D | QA: ende-til-ende-rettekjede og avstemming | S05-A/C, S04-B | Kvittering → feil minimum → retting → korrekt listepris, også etter cold start og nettbrudd |

**Test:** Tom OCR, manglende butikk/dato, separat rabatt, pant, retur, 500 linjer, bildeutløp, samtidig retting, sletting under OCR, navigering med ulagret kladd, TalkBack og stor skrift.  
**Kodeområder:** `ui/receipt/ReceiptScreens.kt`, `ReceiptViewModels.kt`, `backend/app/parsers`, `services/ocr_service.py`, `services/receipt_service.py`, `worker/tasks.py`.

---

## S06. Handleliste som fungerer i butikken

**Problem:** Den sentrale handlingen i produktløftet mangler.  
**Mål:** Opprett liste med tidligere varer på under 90 sekunder, og bruk den uten nett. Dette er et produktmål, ikke dagens målte ytelse.

### Omfang

- Én aktiv liste som standard, med navn, arkiv og «Ny liste». Datamodellen støtter flere lister; avansert listestyring er ikke nødvendig først.
- Legg til fra «Kjøp igjen», søk, tidligere kvittering eller prisdetalj.
- Tillat fritekst for nye varer, merket «Ingen prishistorikk». Brukeren skal slippe en ekstra notatapp for melk som aldri tidligere ble registrert.
- Historiske linjer peker til privat produkt-ID. Vis pakningsstørrelse. Standardmengde er 1 pakning; brukeren kan velge eksplisitt å gjenbruke tidligere mengde. Vektvarer må ha oppgitt enhet.
- Samme produkt/enhet legges som standard på eksisterende linje ved å øke mengde, med angre. Fritekst slås ikke automatisk sammen med et kjent produkt.
- Endre mengde, fjern med angre, kryss av og flytt manuelt. Avkryssete varer vises nederst og kan gjenåpnes.
- «Fullfør handletur» arkiverer listen etter brukerens valg. Uavkryssede varer kan beholdes i ny liste. Avkryssing alene fullfører ikke listen.
- Offline fungerer visning, tillegg fra cache/fritekst, mengde, avkryssing og fjerning. Første kataloghenting og nye prisberegninger trenger nett.

### Datamodell og synkronisering

- `ShoppingList`: id, eier, navn, status (`active`, `archived`), versjon, opprettet/endret.
- `ShoppingListItem`: id, liste, privat produkt-ID eller fritekst, ønsket mengde/enhet, avkrysset, posisjon, versjon og slettemarkør.
- Room-tabeller for lister, linjer, begrenset produkt-/pris-cache og mutasjonsoutbox.
- Lokale handlinger lagres transaksjonelt før UI bekrefter dem. Mutasjoner settes som eksplisitte feltverdier, ikke «toggle», slik at retry ikke krysser av og på.
- Server gir inkrementell sync med cursor. Slettemarkører beholdes i foreslått 90 dager. Utløpt cursor gir krav om fullt snapshot; ventende lokale endringer bevares og avklares før ny avspilling.
- Mutasjon per linje bruker forventet versjon. Uavhengige linjeendringer kan synkes separat. Konflikt på samme linje viser lokale/serververdier; ingen stille last-write-wins for mengde eller sletting.
- Ved konflikt mellom arkivering/sletting av liste og lokal redigering beholdes lokal utgave som gjenopprettbart utkast; aldri gjenoppliv en slettet serverliste automatisk.
- Prisrespons er avledet og kan feile uten at selve listen blir utilgjengelig.

### API og oppgaver

CRUD under `/v2/shopping-lists` og `/v2/shopping-lists/{id}/items`, samt dokumentert `/v2/sync` for lister. Maks 200 aktive linjer per liste i første versjon; valider på begge sider og bevar utkast ved grensefeil.

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S06-A | Backend: lister, eierskap, CRUD, idempotens og syncprotokoll | C00, S03-A | Samme mutasjon gir én effekt; fremmed produkt/liste avvises; arkiv/slettemarkør og cursor testes |
| S06-B | Android: Room/outbox, repository og konflikthåndtering | C00, låst S06-A-kontrakt | 20 offline-endringer overlever appstopp og synkes én gang; konto B får ikke konto A sin liste; konflikt mister ikke lokal endring |
| S06-C | Android: liste-UI og legg-til-flyt | S06-B, S03-C | 10 tidligere varer kan legges til uten fritekstinntasting; en ukjent vare kan legges til uten pris; avkryssing fungerer uten nett |
| S06-D | Android/backend: arkiv, kopier liste og kvittering-til-liste | S06-A/C, S05-A | Kopi har nye ID-er og ukryssede linjer; kvitteringens pris kopieres ikke som nytt kjøp; slettet produkt vises som gjenopprettbar fritekst uten pris |

**Test:** Flymodus, prosessdød, dobbelt trykk, flere enheter på samme konto, sletting kontra lokal endring, utløpt cursor, 200 linjer, tilbakeføring av angre, kontoendring under sync.  
**Kodeområder:** Nye `ui/shoppinglist`, liste-repositories, Room-entiteter/DAO-er, DTO-er og backend `models`, `schemas`, `routers`, `services`. Behold eksisterende arkitekturstil; ikke introduser et nytt app-rammeverk.

---

## S07. Historisk pris i handlelisten og praktisk butikkvalg

**Problem:** Prishistorikken finnes, men er ikke koblet til handlebeslutningen. En ren minimumssum kan dessuten sende brukeren til mange butikker på feil premisser.  
**Mål:** Vis hvor brukeren selv har betalt minst per vare, uten å utgi historiske tall for aktuelle tilbud.

### P0: per vare

- Listekort viser varenavn/pakning, ønsket mengde, avkryssing og «Lavest registrert: … hos …», kjøpsdato/alder og prisgrunnlag.
- Bare én kvalifisert butikk: «Registrert hos … — ingen butikksammenligning ennå».
- Manglende data: «Ingen sammenlignbar pris», med konkret årsak. Ingen 0 kr, tomt felt eller spinner som aldri blir ferdig.
- Trykk viser historisk minimum, siste observasjoner, vilkårsfilter og kilde. Vis alle delte førsteplasser uten vilkårlig anbefaling.
- Ett batchkall for listeprising, ikke ett API-kall per vare. Hele listen returneres med både kvalifiserte og manglende resultater.
- Ved gammel cache vises sist hentet og mulighet til oppdatering. Hvis oppdatering feiler, behold merkede cachedata.

### P1: én-butikkestimat

- Brukeren velger blant egne identifiserte butikker; appen krever ikke GPS og later ikke som den kjenner avstand eller lager.
- Per butikk: bruk **siste kvalifiserte registrering**, ikke laveste observasjon gjennom tidene, for hver vare. Kall resultatet «Historisk estimat — ikke dagens tilbud».
- Multipliser med ønsket mengde/enhet. Pant/ukjente tillegg merkes eksplisitt som utelatt. For vektvarer er sum et estimat av ønsket vekt, ikke en faktisk kjøpssum.
- Prisdekning oppgis som antall prisede linjer av alle aktive, uavkryssete linjer, eksempelvis 6/8. Tallet omfatter også fritekstvarer i nevneren.
- En butikk med 6/8 skal aldri rangere som billigere enn en med 8/8 bare fordi to priser mangler. Vis delsummer uten vinnermerking når det ikke finnes sammenlignbar full dekning.
- Sammenlign fullstendige butikkestimater bare for identisk vareutvalg, mengder, valuta og vilkårsfilter. Vis datoalder og varsler per vare. Hvis siste pris samme dag er usikker, vis sumintervall og ikke en entydig vinner ved overlapp.
- Første butikkestimat utelater alltid vilkårspriser, også når brukeren har slått dem på i den historiske detaljvisningen. Modellen har foreløpig ikke nok informasjon til å kontrollere terskler/medlemskap/kuponger for neste kjøp. «2 for 40» kan derfor vises som historisk kjøp, men kan ikke gi 20 kr i estimat for én pakke. Støtte for slike estimater krever en egen spesifikasjon for vilkår og mengdeterskler.
- Ikke presenter summer av ulike butikkers minimum som en gjennomførbar «billigste handletur». Optimalisering på tvers av butikker er utenfor denne leveransen.

### API og oppgaver

`GET /v2/shopping-lists/{id}/price-summary?include_conditional=false` returnerer versjoner, hver linjes status/kilder, historisk minimum og eventuelle butikkestimater med dekning, manglende linjer, totalsum eller intervall og datoalder. Faste testeksempler skal følge OpenAPI-kontrakten.

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S07-A | Backend: batchprising av liste | S04-B, S06-A | 100 linjer hentes uten N+1-spørringer; alle linjer får status; respons gjenspeiler én konsistent liste-/prisdataversjon |
| S07-B | Android: prisfelt, kildevisning, lastings-/cachetilstander | S07-A, S06-C | Prisfeil blokkerer ikke avkryssing; gammel respons kan ikke overskrive ny liste; ukjent pris vises aldri som null |
| S07-C | Backend/Android: P1 butikkestimat med dekning | S07-A/B | 6/8 kan ikke vinne mot 8/8; historisk minimum brukes ikke i siste-pris-estimat; vilkår og enheter testes |
| S07-D | QA: gylne sammenligningsscenarioer og brukerforståelse | S07-A/B | Hele kjeden matcher manuelt beregnede fixtures, og brukertest skiller historikk fra dagens pris |

**Testscenario:** Butikk A har begge varer til 20 og 30. B har bare første til 15. Listen skal vise 50 for A og «15, pris for 1/2» for B — ikke «B er billigst». Legg deretter til andre vare hos B til 40: sammenlignbare historiske estimater er 50 og 55. Endre A sin første pris fra gammel 20 til nyere 25: minimum og estimat skal divergere, ikke endres til samme begrep.

**Ytelsesmål:** Foreslått p95 under 1 sekund for 100 linjer ved definert staginglast; dokumenter datasett, antall samtidige kall og maskinstørrelse. Dette er en leveransemåling, ikke dagens måleresultat.

---

## S08. Gjenbruk og frivillig kvitteringsvane

**Problem:** Appen må brukes både før og etter handling, ellers stopper datagrunnlaget. Påminnelser alene skaper ikke verdi.  
**Mål:** Gjenbruk sparer tid; diskret oppfølging hjelper brukeren å holde historikken oppdatert.

### Krav

- «Kjøp igjen» sorterer egne varer etter siste kjøp eller kjøpsfrekvens, med tydelig produktidentitet. Ingen antakelse om automatisk gjenkjøpsdato basert på sensitive varekategorier.
- Kopier tidligere kvittering/liste med flervalg; ikke inkluder pant/retur/rabatt som varer. Vis og la brukeren bekrefte mengdene.
- Etter eksplisitt fullført handletur: «Vil du legge til kvitteringen?» med kamera, galleri eller «Ikke nå».
- P1: «Minn meg på senere» krever aktivt valg, ønsket tidspunkt og eventuell varslingsrettighet i kontekst. Ingen push/posisjon/sporing i bakgrunnen nødvendig.
- Maks én påminnelse per avsluttet tur. Avslag gir ingen gjentatt rettighetsmasing. Varsel avbrytes ved logout, valgt avlysning eller registrert kvittering for turen.
- En valgfri `shopping_trip_id` kan koble opplasting til turen. Ingen automatisk vare-/prisbekreftelse ut fra denne koblingen.
- Resultat etter review fokuserer på reell verdi: «Prishistorikken er oppdatert for N varer», ikke udokumentert «Du sparte X».

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S08-A | Android/backend: gjenbrukshandlinger og kjøpsfrekvens | S03-C, S06-D | Tre tidligere kvitteringer kan bli ny liste uten dublerte avgiftslinjer; ordning er stabil ved like kjøpsdatoer |
| S08-B | Android: P1 turavslutning og valgfri lokal påminnelse | S06-D, S02-A, S09-B | Ingen tillatelsesdialog før brukervalg; avvist rettighet blokkerer ikke appen; varsler gjentar ikke samme tur |
| S08-C | Android/backend: kobling tur/kvittering og ærlig bekreftelseskvittering | S08-A, S05-A | Kobling oppretter ikke priser før review; ett bilde kan ikke stille fullføre flere turer |

**Test:** Ingen kvittering etter tur, dobbelt turavslutt, avvist varsling, endret klokke/tidssone, logout og gjenåpning, flere kvitteringer fra én tur. Måling av gjenbruk er S10; ikke innfør et separat analytics-SDK her.

---

## S09. Konto, personvern og brukerens kontroll

**Problem:** Kvitteringer avslører kjøpsvaner og kan inneholde medlems-/betalingsfragmenter. Konto uten god gjenoppretting og sletting er ikke lanseringsklar.  
**Mål:** Brukeren vet hva som lagres og kan komme inn igjen, eksportere og slette.

### Krav

- Konfigurer Google-innlogging i aktuelle miljøer eller skjul knappen. Ikke vis en kjent uvirksom innloggingsmetode.
- E-postgjenoppretting med kortlevd, engangs, hash-lagret token; samme utadrettede svar for eksisterende/ukjent adresse og ratebegrensning. Gyldig tilbakestilling invaliderer gamle sesjoner.
- Backend avviser usikker standard-JWT-hemmelighet i produksjonsmodus. Google-kobling krever verifiserte claims og eksplisitt trygg linkingpolicy; ikke ta kontoeierskap fra lik e-posttekst alene.
- Serverstyrt refresh-rotasjon/tilbakekalling, logout og logout-all. Raced refresh-kall må ha definert håndtering og tester, ikke logge ut brukeren tilfeldig.
- Innstillinger: innlogget konto, personvern, data/lagring, eksport, hjelp, logout og «Slett konto».
- Vis originalbildets utløpsdato. Foreslått policy: originalbilder og rå OCR slettes etter 30 dager; strukturert egen historikk beholdes til bruker sletter. Revisjoner skal heller ikke beholde rå OCR skjult etter denne fristen. Endret retention må godkjennes og kommuniseres.
- Eksport: egne strukturerte kvitteringer/linjer/priser/lister i maskinlesbart format; bare fortsatt lagrede bilder kan inkluderes. Kortlevd nedlastingslenke, eierkontroll og tydelig utløp.
- Kontosletting i app og fungerende webside som ikke krever reinstallasjon. Sikker identitetsbekreftelse, tydelig oversikt over data som slettes og mottaksbekreftelse.
- Sletting setter kontoen til sperret/slettende, tilbakekaller tokens og stopper jobber umiddelbart. Bakgrunnsjobb sletter kvitteringer, objekter, private produkter/aliaser, priser, lister og eksportartefakter med retry. En OCR-jobb skal ikke kunne gjenopprette data etterpå.
- Foreslått tjenestemål: sletting i aktive systemer innen 24 timer; sikkerhetskopier utløper innen 30 dager. Dette er en policy som må dokumenteres og teknisk bekreftes før den loves. Restore-prosedyren må anvende slettemarkører før gjenåpning.
- Android: eksplisitte backup-/cache-regler. Tokens og kvitteringsbilder skal ikke utilsiktet inngå i backup eller bli synlige for annen konto. Vurder Keystore-basert beskyttelse ut fra trusselmodell, ikke som erstatning for app-/serverautorisasjon.
- Ingen kvitteringsbilder, varetekster, summer, butikknavn, søketekster, e-post eller tokens i produktanalytics. Support får ikke automatisk råkvitteringen.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S09-A | Backend: auth-herding, passordreset, sesjoner og rategrenser | C00 | Svak prod-konfig avvises; reset-token kan ikke gjenbrukes; claims/linking/race/revocation har tester |
| S09-B | Android: innstillinger, resetflyt, cache-/backup-/logoutpolicy | S09-A og avtalt kontrakt | Google skjules uten konfig; kontobytte isolerer data; varsler/workers/cache følger kontoen |
| S09-C | Backend: eksport, kontoslettingsjobb, retention og jobbfencing | S03-A, S10-B | Sletting med utilgjengelig objektlager fullføres senere; gjenkjørt jobb er trygg; ingen jobber gjenoppliver konto/data |
| S09-D | Android + enkel webflate: eksport/sletting med bekreftelse og status | S09-C | Kontosletting kan startes både i app og nettleser uten reinstallasjon; feil gir sporbar mottaksstatus uten datalekkasje |
| S09-E | Produktansvarlig/drift, ikke kodeagent alene: policy, e-postavsender, OAuth, Data Safety og backupkrav | S09-A–D | Faktiske systemer og skjema beskriver samme behandling; kontaktpunkt og slettewebside er testet |

**API-forslag:** `/auth/password-reset/request`, `/auth/password-reset/complete`, `/auth/logout`, `/auth/logout-all`, `/v2/me/exports`, `DELETE /v2/me`, statusressurs for slettingsforespørsel med begrenset tilgang.

**Test:** IDOR på alle ID-er inkludert nested produktkobling, token-replay, reset enumeration, sletting under OCR/sync/eksport, objektlagerfeil, backup-restore med slettelogg, konto B etter A sin logout. Produksjonens faktiske hemmeligheter skal ikke leses eller skrives ut av kodeagentene.

---

## S10. Kvalitet, drift og produktlæring

**Problem:** En god normalflyt er ikke nok. Uoppdagede prisfeil, krasj og fastlåste kvitteringer koster brukertillit.  
**Mål:** Målbar brukeropplevelse, etterprøvbar kvalitet og en drift som kan gjenopprettes.

### Android-kvalitet

- Material-komponenter med minst 48 dp berøringsmål, TalkBack-etiketter/tilstand, logisk fokus, lesbar feilmelding og informasjon som ikke formidles bare med farge.
- Test 200 % skrift, liten skjerm, landskap, tastatur, mørkt tema og minst én bred skjerm. Ingen avgjørende knapp utenfor tilgjengelig scrollområde.
- Liste kan åpnes fra lokal cache uten nett. Foreslått mål p95 under 1 sekund for listevisning og lokal avkryssing visuelt innen 100 ms på navngitt referanseenhet.
- Test faktisk minste støttede Android-versjon, en mellomversjon og nyeste stabile, på emulator og minst én fysisk Samsung samt én annen fysisk enhet. Beslutning om lavere minSdk tas fra målgruppe/data, ikke antakelser.
- Ikke sett ny targetSdk-verdi fra dette dokumentet; kontroller gjeldende Play-krav ved release. Sikre edge-to-edge/insets, system tilbake og tillatelser for valgt nivå.

### Backend og drift

- Transaksjonell outbox for kølegging: DB-commit og hensikt om OCR-jobb er atomiske. Dispatcher/reconciler gjenoppretter uteblitte leveranser.
- OCR bruker korte tilstandstransaksjoner, `attempt_id`/lease og fencing. `processing` committes før langvarig arbeid. Sluttresultat skrives bare hvis forsøk og kontostatus fortsatt er gyldig.
- Skill retrybare driftsfeil fra permanente bilde-/parserfeil, begrens forsøk og lagre trygg feilkode. Lange jobber må ikke holde kvitteringsrad låst hele tiden.
- Opprydding/sletting i batch med retry per objekt. Én filfeil stanser ikke alle. Finn foreldreløse objekter etter definert karantenetid, aldri slett blindt etter et ufullstendig listekall.
- Readiness gir 503 ved manglende nødvendige avhengigheter. Separat liveness. Mål Redis, worker/scheduler-livstegn, køalder, OCR-latens, feilrate og eldste uferdige sletting.
- Verifisert PostgreSQL-backup og restore, migreringslås og tydelig enkelt-eier av produksjonsmigrering. Ikke anta skjemaversjon bare fra at en tabell finnes.
- Lokal utviklingskonfigurasjon er ikke produksjonsstandard: ingen eksponerte standardpassord, offentlig objektbucket eller debuglogging i prod. Kontroller faktisk oppsett separat.

### Måling uten kvitteringsinnhold

Foreslåtte hendelser: `capture_started`, `upload_completed`, `review_opened`, `review_confirmed`, `list_created`, `historical_item_added`, `list_used`, `trip_completed`, `price_source_opened`, `flow_failed`.

- Definer `list_used` som en brukerhandling i listen, ikke bare bakgrunnssync. `historical_item_added` skal ikke trigges av demo eller serverretry.
- Tillatte felter: appversjon, plattformversjon, flyt-/hendelses-ID, varighet, antall i intervaller, årsakskode, prisdekningsintervall og samtykkestatus der aktuelt.
- Idempotente event-ID-er, eksplisitt utelukkelse av demo/testkontoer og kjent nevner for hver trakt.
- Skille driftsmåling fra valgfri produktanalyse; dokumenter behandlingsgrunnlag, retention og databehandlere før SDK tas i bruk. Manglende samtykke blokkerer ikke kjernen.
- Rapportér krasj og ANR med sanitert innhold; kvitteringsskjermbilder og fritekst skal ikke følge automatisk med.
- Lag dashboard for aktivering, review-tid, gjentatt listebruk, søk uten treff som antall (ikke tekst), ekskluderte prisårsaker og kvitteringsfeil. Ikke bruk estimert besparelse som dokumentert effekt.

### Oppgaver

| ID | Agent og omfang | Avhengigheter | Akseptansekriterier |
|---|---|---|---|
| S10-A | QA/plattform: CI, PostgreSQL-teststack og migreringskontroll | Ingen; kan starte først | Backendtester, Android unit/lint/build og API-kontrakter kjører på PR; frisk DB og oppgradering testes |
| S10-B | Backend: outbox, forsøk/fencing, reconciler, readiness og robust sletting | C00 | Redis-nedetid etter commit mister ikke jobb; worker-krasj gir ikke dobbelt resultat; slettet konto kan ikke gjenopplives |
| S10-C | QA/Android: kritiske E2E-, tilgjengelighets- og ytelsestester | S02, S05–S07 normalflyt | Registrer → review → liste → pris → offline → retting består; TalkBack/200 %/enhetsmatrise dokumentert |
| S10-D | Android/backend: hendelseskontrakt og sanitert observability | C00, S09-policy | Ingen forbudte felt i logg/event fixtures; retry dobbeltteller ikke; personvernvalg respekteres |
| S10-E | Drift/QA: restoreøvelse, alarmer, staging og release-runbook | S10-A/B, S09-C | Restore målt; testvarsler når riktig eier; release har stopp/rollback og bakoverkompatibel server |
| S10-F | Produkt/QA: kvitteringsbenchmark og pilotanalyse | S05-B, S10-D | Samtykket/anonymisert datasett med eksakt fasit, resultater per butikk/format og protokoll for nye feil |

### Testdata og kvalitetsporter

- Før pilot: minst 30 ulike, lovlig innsamlede/anonymiserte kvitteringer fordelt på minst tre av målgruppens dagligvarekjeder, med vekt, pant, rabatter, lange kvitteringer og vanskelige bilder. Separate utviklings- og holdout-eksempler. Ikke påstå kjedestøtte fra én kvittering.
- OCR-mål rapporteres separat for varenavn, netto beløp, enhet, dato, butikk og antall manuelle rettinger. Automatisk matching må måles på falske sammenslåinger, ikke bare treffprosent.
- Foreslått pilotport: minst 95 % korrekt netto linjebeløp for lesbare holdout-kvitteringer i dokumenterte formater; ingen kjente kritiske feil i enhet/identitet som slipper gjennom kvalifiseringsreglene. Små datasett gir ikke statistisk garanti.
- Foreslått releaseport: minst 99,5 % krasjfrie sesjoner i pilot der utvalget er tilstrekkelig, ingen åpne kritiske data-/sikkerhetsfeil, alle kritiske automatiserte scenarioer grønne og ingen blokkerende tilgjengelighetsfunn. Dette er interne mål, ikke Google-terskler.
- Play Console må ha fungerende reviewer-tilgang, korrekte skjermbilder/beskrivelser, personvern- og slettelenker, gjeldende Data Safety og signert AAB. Utrulling er manuelt godkjent og trinnvis med klart stoppkriterium.

### Verifikasjonskommandoer

Kjør fra angitt katalog, ikke mot produksjonsdata:

- `backend`: `.venv/bin/python -m pytest -q`
- `backend`, disponibel lokal stack: `PRISLAPP_TEST_URL=http://localhost:18000 .venv/bin/python -m pytest tests/test_live_pipeline.py -v`
- `android`: `./gradlew assembleDebug testDebugUnitTest lintDebug`
- `android`, emulator mot disponibel stack: `./gradlew connectedDebugAndroidTest -PapiBaseUrl=http://10.0.2.2:18000/`

Nye PostgreSQL-/migrerings-/benchmarkkommandoer legges i README av S10-A. Eksisterende SQLite-tester er nyttige, men ikke tilstrekkelige bevis for låser, samtidighet, Decimal eller migrering. Ikke rapporter gamle testrapporter som ny kjøring.

---

## 11. Avhengigheter, agentbrief og felles ferdigkriterier

### Eksplisitt pilotomfang

- **P0:** C00; S01-A–C; S02-A–D unntatt beskjæring/langkvitteringsverktøy; S03-A–D; S04-A–D; S05-A–D; S06-A–D; S07-A/B/D; S08-A/C; S09-A–E; S10-A/B/D/E/F og pilotdelen av S10-C.
- **P1:** S07-C; S08-B sin varslings-/påminnelsesdel; utvidet bildehjelp i S02-B; utvidet enhetsmatrise i S10-C.
- Grunnleggende «Fullfør handletur» og oppfordringen om kvittering er P0, eies av S06-D/S08-C og trenger ingen varslingsrettighet. S08-B legger bare den valgfrie senere påminnelsen oppå denne flyten.
- S10-C sin P0-matrise: minimum og nyeste støttede Android på emulator, minst én fysisk referanseenhet, TalkBack, 200 % skrift og kjernens offline/prosessdød. P1 utvider til mellomversjon, både fysisk Samsung og annen produsent, bred skjerm og full ytelsesmatrise før bred release. Grunnleggende layout må fortsatt tåle ulike vindusstørrelser i pilot.

### Start versus godkjent integrasjon

Tabellenes avhengigheter er minimum for å starte. Android kan starte mot låste fixtures, men dette betyr ikke at funksjonen er ferdig integrert. I tillegg gjelder:

- S03-C sin produktretting godkjennes først mot S03-B og S05-A. S03-B eier identitetsoperasjonene; S05-A eier kvitteringsrevisjonen og publisering av observasjoner. S03-C skal ikke lage en alternativ rettebane.
- S01-B godkjennes først med S06-C/D, ikke bare liste-repository/API.
- S06-D eier kopieringsoperasjonen fra kvittering til liste; S01-B og S08-A gjenbruker denne, ikke egne kopieringsalgoritmer.
- Alle frontendoppgaver som bygger mot fixtures trenger senere kontrakt- og integrasjonstest mot faktisk backend før ferdigmelding.

### Praktisk gjennomføring

1. **Først:** C00 og S10-A. Samtidig kan S09-A og avgrenset reparasjon av S02-A starte uten å vente på handlelistedomenet.
2. **Fundament:** S03-A → S04-A → S05-A. S10-B og S09-C utvikles sammen om kø-/slettingskontrakten. Unngå to agenter som samtidig omarbeider `receipt_service.py`.
3. **Parallelt etter låst kontrakt:** Backend S06-A og Android S06-B/C mot kontraktfixtures. S03-C og S05-C kan bygges i egne, avgrensede moduler.
4. **Vertikal kjede:** S04-B → S07-A/B, S01-B og S06-D/S08-A. Integrer tidlig; ikke vent på at alle delene skal være «ferdige» hver for seg.
5. **Før ekstern pilot:** Alle P0-akseptansekriterier, S09, relevante S10-porter og manuell brukerprøving.
6. **Etter bevist nytte:** S07-C, S08-B og utvidet bilde-/formatstøtte.

Backendens modell-/migrasjonsendringer serialiseres av én integrasjonseier. Androids Room-versjon og navigasjon har tilsvarende eier. API-kontrakter, fixtures og versjoner er felles leveranser, ikke private valg per agent.

### Mal som kan gis til en kodeagent

> Implementer oppgave [ID] i `docs/produktspesifikasjoner-2026-09-11.md`. Les del 0, relevant spesifikasjon, avhengighetene og gjeldende prosjektinstruksjoner. Ikke implementer nabofunksjoner. Start med tester som demonstrerer manglende oppførsel. Avklar kontraktsbrudd før endring. Bruk eksisterende Kotlin/Compose/Room/WorkManager- og FastAPI/SQLAlchemy/Celery-arkitektur. Lever kode, migrasjoner der nødvendig, kontraktfixtures, tester og kort verifikasjonsrapport. Ikke deploy, publiser, endre secrets eller kjør destruktivt mot produksjon. Oppgi hva som er verifisert, hva som er blokkert og hvilke manuelle steg som gjenstår.

### Definition of Done for hver kodeoppgave

- Akseptansekriteriene er demonstrert med nye tester; relevante eksisterende tester består.
- Feil-, tom-, offline- og kontobyttetilstand er vurdert for endringen.
- Autorisasjon omfatter både ressurs-ID og alle innsendte referanse-ID-er.
- API-/datamodellendringer har kompatibilitetsstrategi, indekser, migrasjonstest og rollback-/forward-fix-plan. Rå kjøpsgrunnlag går ikke tapt.
- Norske tekster ligger i ressurser der det passer. Skjermleser og stor skrift er kontrollert for endret UI.
- Ingen secrets eller personlige kvitteringer i kode, fixtures, logg eller rapport.
- PR-/leveranserapport oppgir faktiske kommandoer/resultater. Ikke attestér Play-godkjenning, produksjonsdrift eller målt brukeradopsjon fra enhetstester.
- Menneskeeide lanseringsoppgaver er eksplisitt åpne frem til ansvarlig har bekreftet dem.
