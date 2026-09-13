# Penger, mengder og avrunding

Implementert i `backend/app/domain/money.py` og `backend/app/domain/units.py`. Android bruker `java.math.BigDecimal` med identiske kvanta.

## Transport

- JSON bruker **desimalstrenger**, aldri `number`.
- Backend: `decimal.Decimal`. Android: `BigDecimal`. Ingen flyttallsregning for penger.

## Presisjon

| Verdi | Kvanta | Merknad |
|---|---|---|
| Betalte NOK-linjebeløp | 2 desimaler | `0.01` |
| Mengder | inntil 3 desimaler | `0.001` |
| Sammenligningspris | 6 desimaler | `0.000001`, lagres før visning |
| Visning / sluttbeløp | 2 desimaler | `ROUND_HALF_UP` |

Rund **ikke** underveis i kjeden. Rund først ved visning eller avtalt sluttbeløp.

## Formler

- Pakningsvare: `net_line_total / package_count` → `price_basis = per_package`.
- Vekt/volum: `net_line_total / normalisert kg eller l` → `per_kg` / `per_litre`.
- Normaliser g→kg og ml→l før sammenligning. **Aldri** stk→kg uten kjent pakningsinnhold.
- `printed_unit_price` er et lest felt, ikke fasit. `net_line_total` er beløpet som inngår i observasjonen.

## Enums

- `quantity_unit`: `each`, `kg`, `g`, `l`, `ml`, `unknown`
- `line_type`: `product`, `deposit`, `fee`, `discount`, `return`, `unknown`
- `price_basis`: `per_package`, `per_kg`, `per_litre`, `unknown`
- `condition`: `none`, `member`, `multi_buy`, `coupon`, `unknown`

Pant/gebyr/retur inngår ikke i vareminimum. Ukjent rabattfordeling gir ingen rangerbar pris. Gratisvarer er historikk, ikke standard råd. Utenlandsk valuta arkiveres, men utelukkes fra sammenligning. Ingen valutakonvertering i P0.

## Alder

Beregnet fra `purchase_date`, ikke `uploaded_at`/`confirmed_at`:

- 0–30 dager: «registrert nylig»
- 31–90 dager: «eldre observasjon»
- over 90 dager: «gammel observasjon»

Alle visninger inkluderer faktisk dato og «Dagens pris kan være annerledes».

## Fixtures

Se `fixtures/rounding.json`, `two-packages.json`, `kg-item.json`.
