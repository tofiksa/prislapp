# OCR-02 — felles norsk pengetolking og riktig totalsum

## Selvstendig oppdrag

I Prislapp kan korrekt OCR-tekst gi feil total. Ved baseline `4bb0dcb` forventer Rema-parseren `Sum N varer`, mens generisk parser stopper ved første total-lignende linje. Begge kan erstatte ufunnet total med varesum. `TOTALT 1 234,50` kan bli tolket som en vare til 234,50 og gi feil sum.

Arbeid i `~/workprojects/prislapp/backend`. Les `../docs/ocr-backend/README.md`, kontrakten fra OCR-01 og overleveringene fra **OCR-00 og OCR-01**, som er nødvendige avhengigheter.

## Filer og eierskap

Les `app/parsers/{generic,rema1000,retail,base}.py`, `app/domain/money.py`, `tests/test_rema1000_parser.py` og nye OCR-fixtures. Implementer nye felles moduler, foreslått `app/parsers/amounts.py` og `app/parsers/totals.py`. OCR-06 eier koblingen til dispatch og fjerning av gamle fallbacker; ikke lag parallelle nye totalregler i hver kjedeparser.

## Krav

1. Ren funksjon for penger: `20,00`, `20.00`, `1 234,50`, NBSP/smalt NBSP og dokumenterte former som `NOK 1.234,50`/`kr 20,00`. Bevar fortegn. Tvetydig `1.234` uten desimal-/valutakontekst blir ikke blindt 1234 eller 1,23. Ukjent format gir kandidatfeil, ikke exception fra hele kvitteringen.
2. Skill pengekolonner fra antall, dato, org.nr., MVA-prosent og strekkode. Ikke «ta siste tall i strengen» som generell regel.
3. Samle **alle** totalkandidater før valg. Støtt `TOTAL`, `TOTALT`, `Å BETALE`, `TIL BETALING`, `I ALT KR.`, `SUM N VARER` og dokumenterte variasjoner. Normalisering beholder kilde og endringer.
4. Knytt etikett til beløp på samme rad eller nærliggende rad/kolonne med strukturert bevis. Tekst-only fallback kan bruke neste rad hvis entydig og ingen ny seksjon begynner. Flere mulige beløp gir usikkerhet.
5. Skille endelig handelssum fra mellomsum før rabatt, MVA-beløp, MVA-grunnlag, kortterminalbeløp, kontant mottatt og vekslepenger. Et stort `KONTANT 500,00` vinner aldri fordi tallet er størst.
6. Kontant/gavekort/delt betaling kan bekrefte konsistens, men er ikke i seg selv en trykt handelssum. Eventuell avledet betalingssum holdes separat fra `printed_total`.
7. Bruk etikett/område, seksjonsgrenser, støtte fra identiske beløp og vareavstemming som forklarbare signaler. Ikke la en ufullstendig varesum overstyre tydelig sluttotal.
8. Returner kandidater, valg, årsaker og ID-ene til brukte totallinjer, så vareparseren kan ekskludere dem. Ikke kast kandidatlisten etter første treff.
9. Manglende/ambivalent trykt total gir null. Beregnet varesum er et eget felt med fullstendighetsstatus. Negative returkvitteringer bevares internt, men må ikke settes positivt eller presses inn i legacybekreftelse som ikke støtter dem; kontrakten markerer behov for støttet review.

## Obligatoriske tester

- De fem totalfeilene i planens kapittel 3, inkludert `1234.50` og korrekt ekskludering av totallinjen som vare.
- Normal: `I alt kr. 100,00`, `Kontant -200,00`, `Vekslepenger 100,00`: handelssum 100,00.
- `SUM 25,00`, `RABATT -5,00`, `TOTALT 20,00`: velg 20,00 uten å late som rabattlinjene er fullstendig parset.
- MVA-tabell med `Totalt 152,08` og `6,75` skal ikke overstyre Rema sin `Sum 7 varer 158,83`.
- Gavekort+kortbetaling, sum før/etter avrunding, to like sluttotaler, to motstridende sluttotaler og total borte ved avskjæring.
- Beløpsetikett og verdi adskilt; støy mellom dem skal ikke knytte vilkårlig beløp til total.
- Pengetall uten kvitteringskontekst, negative beløp, nulltotal og ekstremt lange tall skal håndteres kontrollert.

## Akseptanse og verifikasjon

Alle kritiske fixtures gir korrekt total eller forventet avståelse; ingen oppfunnet trykt total. Test funksjonene direkte med OCR-01-dokumenter og tekst-only-adapter; layoutimplementasjonen er ikke startavhengighet. OCR-06 verifiserer ende-til-ende senere.

Kjør nye `tests/test_receipt_totals.py`/pengetester, relevante eksisterende parsere og OCR-00 sin parserbenchmark. Rapporter eksakte resultater og fjern kun de `xfail` som faktisk er løst ved integrasjon.

Lever `docs/ocr-backend/handoffs/OCR-02.md` fra repo-roten: API, beslutningsregler, støttede formater, resultater, uløste tvetydigheter og koblingsinstruks til OCR-06. Ingen DB-/worker-/Androidendring i denne oppgaven.
