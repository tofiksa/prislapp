# Egen backendplan: pålitelig butikk- og totalgjenkjenning

Dato: **13. september 2026**. Kildegrunnlag: Git **`4bb0dcb`**. Status: plan, ikke implementert. Planen kan brukes uten tidligere samtaler eller produktplaner.

## 1. Oppdrag og anbefaling

Prislapp leser brukerens egne kvitteringer for å bygge kjøps- og prishistorikk. Brukeren opplever at OCR ofte bommer, særlig på butikknavn og totalsum. Målet er at backend fyller ut disse riktig oftere, og lar felt være uavklart fremfor å presentere en gjetning som sikker avlesning. Kvitteringer skal fortsatt gjennomgås av brukeren før priser publiseres.

**Anbefaling: reparer tolking og kvalitetskontroll før vi bytter OCR-motor.** Flere feil kan reproduseres med korrekt tekst, uten bilde eller OCR. Bytte av motor alene løser derfor ikke hovedproblemet.

Prioritert strategi:

1. Mål korrekt butikk og korrekt total mot fasit, ikke bare om teksten eller noen varer ble funnet.
2. Innfør felles kandidatbasert total- og butikkgjenkjenning, på tvers av kjedeparsere.
3. Behold tekstbokser, posisjon og OCR-score. Bruk plassering og kvitteringsseksjoner til å skille total, betaling, vekslepenger og MVA.
4. Slutt å erstatte manglende avlest total med sum av gjenkjente varer. Behold beregnet sum som et eget, merket felt.
5. Bevar bildekvaliteten for lange kvitteringer og gjør en begrenset ny avlesning av usikre områder.
6. Integrer kvalitetsresultatene med eksisterende worker, review-API, revisjoner og sletting.
7. Vurder annen OCR-/dokumentmotor med samme testsett hvis gjenstående feil faktisk er avlesningsfeil.

### Hva dette ikke krever

Ingen Android-implementasjon, ekstern prisdatabase, ny handleliste, ny produktmatching eller omskriving av jobbkø. Backend leverer kompatible felt og ny kvalitetsmetadata. Eldre Android får nytte av bedre forhåndsutfylte verdier; visning av nye kandidater/advarsler er en senere klientoppgave og skal ikke påstås levert her.

## 2. Nåværende system — les dette ved oppstart i ny sesjon

Arbeidsområde: `~/workprojects/prislapp`; backend: `backend/`. Stack: Python/FastAPI, SQLAlchemy, Alembic, PostgreSQL, Celery/Redis, MinIO, Pillow, RapidOCR 3.9.2 og ONNX Runtime 1.23.2. Android er Kotlin/Compose. Ingen gjeldende `AGENTS.md` ble funnet under repoet ved undersøkelsen; sjekk igjen før implementasjon.

Flyten ved kildegrunnlaget:

```text
opplasting → MinIO + eksisterende outbox
→ worker claim med attempt_id/lease
→ OcrService.extract_text(bytes)
→ parse_receipt_text(str)
→ complete_ocr_result(...)
→ ReceiptService.save_parsed_receipt(...)
→ READY_FOR_REVIEW → manuell bekreftelse/revisjon
```

| Kode | Viktig nåværende oppførsel |
|---|---|
| `backend/app/services/ocr_service.py:23–45` | EXIF-rotasjon/fargemodus, lengste side skaleres til maks 2500 px. En lang kvittering kan få svært smal tekst. Ingen dokumentutsnitt eller målrettet andrepass. |
| Samme fil `:48–75` | Tekstbokser brukes til enkel radgruppering, men geometri og score kastes før parsing. Bare streng returneres. |
| `backend/app/parsers/base.py` | `ParsedReceipt` har ett butikknavn, ett totalfelt og linjer; ingen kilde, kandidater eller usikkerhet. |
| `backend/app/parsers/generic.py:27–45` | Første ikke-tomme linje blir butikk. Første gjenkjente total avslutter parsing. Ufunnet total erstattes med varesum. |
| `backend/app/parsers/rema1000.py:36–43,80–89` | Butikk krever kjede og filial på samme linje. Total forventer `sum N varer ...`; ellers varesum. |
| `backend/app/parsers/retail.py:9–28` | Smale mønstre for Europris/Normal; butikkfallback kan være bare kjedenavnet. |
| `backend/app/parsers/__init__.py` | Én parser velges tidlig fra kjedenavn. Dette bestemmer også hvilke totalmønstre som blir forsøkt. |
| `backend/app/worker/tasks.py:35–81` | OCR-resultat gjøres til legacy varelinjer og sendes til existing outbox completion. |
| `backend/app/services/ocr_outbox.py` | Outbox, claim, lease, attempt-fencing, gjenoppretting og kontroll av slettet konto er allerede implementert. Bevar disse. |
| `backend/app/services/receipt_service.py:145–177` | OCR-resultatet lagres fortsatt i legacy `Receipt.total`/`Store`/`ReceiptItem`. |
| `backend/app/models/receipt_revision.py` | V2 har allerede `printed_total`, `computed_total` og avstemmingsstatus. Ikke lag en konkurrerende revisjonsmodell. |
| `backend/app/services/receipt_revision_service.py:207–258` | `reconcile` finnes. En ukjent linjetype holdes utenfor; OCR-integrasjon må ikke tolke delvis linjedekning som fullstendig. |
| `backend/app/services/receipt_revision_backfill.py` | Legacy total kopieres til `printed_total`. Tidligere totalsummer kan være beregnede; proveniens kan ikke gjettes i en migrering. |
| `backend/app/config.py:35–40` | Bilde-retention 30 dager, lease 300 sekunder, maks 5 jobbforsøk. Nye OCR-budsjetter må passe innenfor dette. |
| `docs/contracts/` | Eksisterende v1/v2-kontrakter, desimalregler og overgang. Les relevante filer; ikke start produktarkitekturen på nytt. |

Repoet er videreutviklet etter de eldre produktplanene. Bruk faktisk kode som nåsituasjon. Dersom filer/kontrakter er endret siden `4bb0dcb`, registrer avvik i oppgaveoverleveringen før implementasjon.

## 3. Hva som er verifisert, og hva som fortsatt er ukjent

### Kjørte tester

Fra `backend/`:

```bash
.venv/bin/python -m pytest tests/test_ocr_service.py tests/test_receipt_images.py tests/test_rema1000_parser.py -q
```

Resultat: **7 bestått**, ca. 12 sekunder, én eksisterende pytest-asyncio-deprecationwarning. Det er ikke kjørt full backend-/PostgreSQL-testpakke som del av planleggingen.

Lokal gjennomkjøring av eksisterende bilder ga:

| Bilde under `testdata/receipts/` | Tolket butikk | Total | Varelinjer |
|---|---|---:|---:|
| `rema1000-metro-senter.png` | REMA 1000 METRO SENTER | 158,83 | 7 |
| `normal-triaden.png` | Normal Oslo, Thon Senter Triaden | 100,00 | 6 |
| `europris-normal-triaden.png` | EP TRIADEN | 39,90 | 1 |

De to hele bildene ble også visuelt kontrollert: 158,83 og 100,00 er de trykte totalene. Europris-bildet er sammensatt/avskåret; resultatet er **ikke** verifisert som korrekt total for hele bildet. Det skal brukes som krevende/negativt tilfelle, ikke som bevis for fler-kvitteringsstøtte.

### Reproduserte tolkningsfeil uten OCR

Disse tekstene ble sendt direkte til `parse_receipt_text`. Punktum i resultatkolonnen representerer `Decimal`.

| Input (`\n` = linjeskift) | Faktisk nå | Riktig mål |
|---|---|---|
| `REMA 1000\nMETRO SENTER\nMELK 15 25,00\nSUM 1 VARER 25,00` | Butikk `None` | Kjede Rema 1000 og eksplisitt filialkandidat Metro Senter |
| `REMA 1000 METRO SENTER\nMELK 15 25,00\nRABATT -5,00\nTOTALT 20,00` | Total `25.00` | Avlest total `20.00`; mangelfull rabatt-/linjetolking varsles separat |
| `KIWI OSLO\nMELK 25,00\nTOTALT\n20,00` | Total `25.00` | Knytt entydig neste beløp til totaletikett; `20.00` |
| `KIWI OSLO\nVARE 99,00\nTOTALT 1 234,50` | Total `333.50`, 2 «varer» | Avlest total `1234.50`; totallinjen er ingen vare |
| `VELKOMMEN\nKIWI OSLO\nMELK 25,00\nTOTALT 25,00` | Butikk `VELKOMMEN` | Butikkandidat KIWI OSLO; «OSLO» er ikke alene verifisert filial-ID |
| `KIWI OSLO\nMELK 25,00\nSUM 25,00\nRABATT -5,00\nTOTALT 20,00` | Total `25.00` | Endelig total `20.00`, ikke første mellomsum |

Dagens bildetester krever ofte bare «varer finnes» eller «total er ikke null». En feil varesum kan derfor passere. Endringer må måles både med og uten OCR for å skille modellfeil fra tolkningsfeil.

**Ukjent:** Hvilke av brukerens øvrige kvitteringer som feiler, produksjonens modellartefakter/ressurser og feilrate i et representativt utvalg. Ikke tilskriv alle opplevde feil én årsak eller lov en prosentsats basert på tre bilder.

## 4. Foreslått ny flyt

```text
bytes → normalisert bilde + transformkart
→ strukturert OCR-dokument (tokens, score, polygoner)
→ rader/kolonner/seksjoner
→ uavhengige butikk- og totalkandidater + eksisterende vareparser
→ kildebasert valg + kvalitetskontroll
→ ved behov: ett begrenset andrepass av relevante utsnitt
→ kvalitet/proveniens + review-data lagret atomisk via existing attempt-fencing
```

### Felles regler

- **Total betyr endelig trykt handelssum**, normalt etter rabatter og inklusive pant/gebyr på kvitteringen. `Kontant`, korttrekk, gavekort, vekslepenger og MVA-totaler er separate beløp; de skal ikke automatisk bli handelssum. Retur/negativ handel må ha en eksplisitt støttet representasjon, aldri gjøres positiv.
- `printed_total=null` når trykt total ikke er funnet entydig. `computed_items_total` kan finnes samtidig, men er aldri uavhengig bekreftelse på seg selv.
- Varesum er et støttesignal, ikke en regel som overstyrer en tydelig trykt total. Summen kan være feil fordi varer eller rabatter mangler.
- Flere like sluttotaler (sum/bank) er støttende bevis. Flere motstridende sluttotaler krever avklaring, ikke «velg største/siste».
- Butikk deles i kjede, observert filialtekst og eventuell sikker privat butikk-ID. Gjenkjent kjede betyr ikke gjenkjent filial. Adresse/org.nr./butikknummer er støttedata, ikke automatisk unik filialidentitet.
- OCR-score er ikke en kalibrert sannsynlighet for at en butikk eller totalsum er riktig. Felttilstand er `accepted`, `uncertain` eller `missing`, med årsaker og kildetokens. `accepted` er et maskinforslag, aldri brukerbekreftelse.
- Originaltekst beholdes ved siden av normalisert tekst. Bokstav→tall-korreksjon tillates bare som merket kandidat i pengekontekst; ikke gjør `O` til `0` i alle produkt-/butikknavn.
- Ingen automatisk sammenslåing av to kvitteringer i ett bilde. Ved konkurrerende dokumenter: varsel og avstå fra felles butikk/total. Brukeren må kunne laste opp et bedre utsnitt; splitting er et eget senere prosjekt.
- Nye OCR-forsøk skal ikke overskrive brukerens lagrede kladd eller bekreftede revisjon.

## 5. Arbeidspakker

Hver lenke er en selvstendig oppgavebrief med bakgrunn, filer, steg, tester og ferdigkriterier. «Selvstendig» betyr at oppgaven kan forstås i et nytt kontekstvindu, **ikke** at alle oppgaver kan implementeres samtidig uten avhengigheter.

| ID | Oppgave | Avhengighet | Prioritet |
|---|---|---|---|
| [OCR-00](tasks/OCR-00-baseline.md) | Fasiter, regresjonssett og måleverktøy | Ingen | P0 |
| [OCR-01](tasks/OCR-01-contract.md) | Strukturert OCR-/feltkontrakt og kompatibilitet | Ingen; samordnes med 00 | P0 |
| [OCR-02](tasks/OCR-02-totals.md) | Norsk pengetolking og robust totalvalg | 00 + 01 | P0 |
| [OCR-03](tasks/OCR-03-stores.md) | Butikk/kjede/filial fra flere evidenskilder | 00 + 01 | P0 |
| [OCR-04](tasks/OCR-04-layout.md) | Tokengeometri, leserekkefølge og seksjoner | 01 | P0 |
| [OCR-05](tasks/OCR-05-images.md) | Bevar lesbarhet; utsnitt og kontrollert andrepass | 00 + 01 + 04 | P1, tidligere hvis måling viser bildefeil |
| [OCR-06](tasks/OCR-06-pipeline.md) | Samlet tolkningspipeline og kvalitetsregler | 02 + 03 + 04 | P0 |
| [OCR-07](tasks/OCR-07-integration.md) | Lagring, review-API, v1/v2 og workerintegrasjon | 01 + 06 | P0 |
| [OCR-08](tasks/OCR-08-engine-evaluation.md) | Kontrollert sammenligning av OCR-alternativer | 00 + 04; anbefalt etter 05/06 | P2, beslutningsstyrt |
| [OCR-09](tasks/OCR-09-release.md) | Ende-til-ende-kvalitet, utrulling og drift | 00–04 + 06 + 07; 05/08 hvis aktivert | P0 |

Start med 00 og 01. Etter låst kontrakt kan 02, 03 og 04 utvikles parallelt i separate filer. 06 eier parser-dispatch/integrasjon; 07 eier worker, lagring, API og migrasjoner. 05 eier bildebehandling; OCR-adapteren i `ocr_service.py` endres av 04 først. Ingen agenter skal konkurrere om samme migrasjonsnummer.

### Leveransetrinn

**A — rask gevinst:** Fasiter, felles total/butikk, fjern skjult sumfallback, og integrer via 06/07. Dette løser flere demonstrerte feil uten modellbytte.

**B — bedre reelle bilder:** Geometri/seksjoner, dokumenttilpasset skalering og målrettet andrepass, valgt ut fra feilklassene i benchmark.

**C — eventuell ny motor:** Bare dersom en kontrollert sammenligning viser tilstrekkelig gevinst etter bedre tolking. Ikke legg inn en ekstern leverandør som standard uten beslutning om kostnad, personvern og drift.

## 6. Mål og beslutningsporter

Mål både eksakt treff på alle lesbare kvitteringer og presisjon blant maskinaksepterte felt. Ellers kan systemet «forbedres» ved å avstå fra alle svar. Rapportér egne tall for manglende, uleselige og avskårne felt; ikke fjern vanskelige bilder fra rapporten.

- Start med de eksisterende bildene og minst 20 syntetiske tekst/layout-regresjoner. Skaff deretter minst 30 unike kvitteringer fra minst tre relevante dagligvarekjeder før bred kvalitetskonklusjon. Be bruker/testansvarlig om feilede eksempler med samtykke.
- Holdout må inneholde andre kvitteringer, ikke bare roterte kopier av trenings-/utviklingsbildene. Alle varianter av samme original ligger i samme split.
- Før en bredere pilot: foreslått mål minst 95 % eksakt avlest total på lesbare støttede holdout-kvitteringer; rapportér antall og usikkerhet. Butikkjede og filial måles separat. Minst 90 % eksakt filialtekst der teksten faktisk finnes lesbart er et startmål, ikke garanti.
- Ingen feilaktig maskinakseptert total i det kritiske settet: kontant/vekslepenger, MVA-tabell, delsum/rabatt, tusenskille og flere kvitteringer. Dette er en fast regresjonsport, ikke et statistisk løfte.
- Dokumenter precision/coverage for butikk og total. Endrede terskler skal evalueres på holdout én gang per kandidat, ikke tunes gjentatte ganger mot testfasit.
- Normalpass og andrepass rapporteres separat med p50/p95, prosessminne, kaldstart og modellversjoner på navngitt maskin. Foreslått OCR-budsjett: 45 sekunder veggklokketid per jobb og maks ett andrepass med maks to utsnitt. Dette må håndheves også for blokkerende native inferens og passe trygt under lease.
- Produksjonsutrulling krever full relevant backendregresjon, PostgreSQL-integrasjon og eksplisitt godkjenning. Ingen live-reprosessering av historikk er del av oppgavene.

## 7. Personvern og datakilder

Eksempelbildene er merket anonymiserte i repoet, men inneholder synlige kvitterings-/betalingsfragmenter og mulig ansattnavn. Ikke kopier dem til eksterne tjenester eller nye rapporter uten ny kontroll. Nye fasiter skal unngå unødvendige personopplysninger. Redigering må bevare butikk og total som skal testes og kan endre OCR-layout; behold derfor dokumentert split-/variantkobling.

OCR-tokens, utsnitt og råtekst kan være like sensitive som originalbildet. Oppgave 07 definerer faktisk retention/sletting for alle nye artefakter. Foreslått er samme 30-dagers frist som originalbildet, uten at retry starter fristen på nytt. Strukturerte, brukerbekreftede kjøpsdata følger eksisterende historikkpolicy. Ingen varig logg av hele OCR-responsen.

## 8. Oppstart i nytt kontekstvindu

Gi kodeagenten denne teksten:

> Arbeid i `~/workprojects/prislapp`. Implementer kun `docs/ocr-backend/tasks/OCR-XX-....md`. Les oppgavebriefen, `docs/ocr-backend/README.md` og filene briefen viser til. Planens baseline er commit `4bb0dcb`; undersøk nåværende kode og avhengighetenes leveranser før endring. Oppgaven skal kunne løses uten tidligere chat. Skriv først regresjonstester som demonstrerer problemet. Bevar eksisterende outbox/fencing, eierskap, v1/v2-overgang og manuell bekreftelse. Ikke deploy, reprosesser produksjon eller send kvitteringer til tredjepart. Lever kode/test/migrasjon ved behov og en overlevering under `docs/ocr-backend/handoffs/OCR-XX.md` med berørte filer, kontraktendringer, testkommandoer/resultater, benchmarkdelta, begrensninger og neste steg. Ikke merk oppgaven ferdig hvis integrasjon eller nødvendig testgrunnlag mangler.

Oppgavene er ikke tildelt eller igangsatt gjennom denne planen. Produksjonskonfigurasjon og ukjente kvitteringer er ikke undersøkt.
