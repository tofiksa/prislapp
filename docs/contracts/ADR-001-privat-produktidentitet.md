# ADR-001: Privat produktidentitet

**Status:** Akseptert for P0  
**Dato:** 2026-09-11

## Kontekst

Dagens `products` / `product_aliases` er globale. Brukerinnsendte aliaser kan koble ulike varer og dele tekst på tvers av kontoer. Prisobservasjoner er allerede brukeravgrenset, men matching er det ikke. Handleliste og «lavest registrert» krever at «samme vare» er eierstyrt og korrigerbar.

## Beslutning

1. Nye flyter bruker privat `UserProduct` og `UserProductAlias` eid av innlogget bruker.
2. Globale `products` / `product_aliases` beholdes som skrivebeskyttet kompatibilitetslag. De er ikke autoritativ match for v2-prising eller handleliste.
3. En fremtidig kuratert global katalog er et separat, valgfritt lag og mottar ikke automatisk brukerens OCR-tekst.
4. Backfill oppretter ett `UserProduct` per eksisterende `(user_id, product_id)` fra bekreftede kvitteringslinjer. Der det ikke finnes sikkert eget grunnlag merkes `identity_status = inherited` (uavklart). Original varetekst bevares.
5. Merge med motstridende variant- eller pakningsdata avvises. Brukerbekreftelse kan ikke gjøre ulike pakninger sammenlignbare.

## Konsekvenser

- Android v2 peker på `user_product_id`, aldri globalt `product_id`, i handleliste og prisoppslag.
- `GET /products/search` og `GET /products/{id}/my-prices` forblir til gjeldende klient er migrert.
- Prisråd på arvet matching ber om avklaring; historikk slettes ikke.
