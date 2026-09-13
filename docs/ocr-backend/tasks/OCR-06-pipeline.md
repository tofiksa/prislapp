# OCR-06 — samle feltgjenkjenning og kvalitetsbeslutninger

## Selvstendig oppdrag

Prislapp velger i dag én kjedeparser tidlig; dens butikk-/totalregler blir fasit, og manglende total kan bli erstattet med varesum. Nye felles butikk-/totalmoduler skal brukes sammen med strukturert OCR, uten å miste eksisterende vareparsing.

Arbeid i `~/workprojects/prislapp/backend`. Les hovedplanen og handoffs for **OCR-01, OCR-02, OCR-03 og OCR-04**. OCR-00 gir benchmark. OCR-05 er valgfri utvidelse, ikke en blokkering for standardpasset.

## Eierskap og filer

Eier ny `app/services/receipt_extraction_service.py` og integrasjonen i `app/parsers/{__init__,base,generic,rema1000,retail}.py`. Les eksisterende `ReceiptRevisionService.reconcile`, men ikke lag en ny konkurrerende bekreftelses-/prisberegning. OCR-07 eier worker/lagring.

## Implementasjonssteg

1. Ren pipeline: dokument/layout → butikk- og totalkandidater → vareparservalg → samlet resultat. Felles totaluttrekk skal brukes også for kjeder med egen vareparser.
2. Velg vareparser konservativt fra butikk-/layoutbevis. Gjenkjent kjede med ukjent vareformat kan bruke generisk vareparser. Lav sikkerhet gir ikke kjedespesifikt tvangstreff.
3. Fjern skjult `sum(items)` som `ParsedReceipt.total` fra Rema/generisk ny flyt. Beregnet sum er separat og kan være ufullstendig. Stopp ved eksplisitt identifiserte seksjoner; total-/MVA-/betalingslinjer skal ikke bli varer.
4. Ved korrekt trykt total og manglende varer: behold totalen, sett `ITEMS_INCOMPLETE`/avvik. Ved manglende total og tilsynelatende komplette varer: trykt total forblir null.
5. Foreslåtte kvalitetsnivåer: felttilstand fra OCR-01 og kvitteringsnivå `review_ready`, `review_required`, `unreadable`. Ikke endre `ReceiptStatus`-enum i denne oppgaven. En kvittering med manglende butikk kan være nyttig i review.
6. Avstemming er rådgivende før brukerbekreftelse. Klassifiser om linjedekningen faktisk er kjent: ukjente/skippede rabatt-/returlinjer gjør avstemming ufullstendig selv om tall tilfeldigvis summerer likt. Ikke «reparer» varebeløp for å få regnestykket til å gå opp.
7. Konkurrerende kvitteringer i ett bilde skal ikke blande en butikks navn med en annens total. Returner tydelig årsak og intet sikkert kombinert resultat.
8. Bevar `parse_receipt_text(str)` med tekst-only dokumentadapter og eksisterende `extract_text`-bruk. Ny pipeline skal kunne testes uten OCR-motor og uten database.
9. Hvis OCR-05 er levert, bruk et injisert andrepass-grensesnitt ved usikre felt; ellers returner standardresultatet med årsak. Ikke implementer alternativ bildebehandling her.
10. Versjoner regelsett og feltvalg. Alle valgte beløp/navn må ha kildereferanse; ingen hardkodet fasit for eksempelbildene.

## Tester

- Alle seks baselinefeil skal løses i den offentlige `parse_receipt_text`-inngangen, ikke bare i isolerte hjelpefunksjoner.
- Rema/Normal sin korrekte butikk/total/varedekning beholdes på de to hele bildene; test eksakte totaler.
- MVA, betaling, rabatter, delsummer og tusenskiller blir ikke varelinjer. Ufullstendige linjer markeres, ikke skjules.
- Flere dokumenter, tom OCR, tekst uten varer, kjent butikk med ukjent format og unknown chain.
- Mock andrepass med bedre, identisk og motstridende resultat; ingen ubegrenset løkke eller «høyeste score alltid vinner».

## Akseptanse og overlevering

Kjør alle parser-/OCR-regresjoner og OCR-00 sin parser- og bildebenchmark. Ingen falsk sikker total i kritisk sett. Ingen akseptanse uten kildebevis. Dokumenter endringen fra tidligere sumfallback, også hvilke gamle tester som med rette ble strammet inn.

Lever `docs/ocr-backend/handoffs/OCR-06.md` med offentlige innganger, resultatskjema, kompatibilitetsatferd, kvalitetskoder, benchmark og presise koblingsinstrukser til workeroppgave OCR-07. Endre ikke brukerbekreftede data eller prisobservasjoner.
