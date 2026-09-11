# Migrasjonsplan (additiv)

P0 skal **ikke** kjøre destruktiv migrering. Rå kjøpsgrunnlag går ikke tapt.

## Rekkefølge

1. **005 (S03-A):** Nye tabeller `user_products`, `user_product_aliases`, `user_stores`, `account_ledgers`. Mapping `legacy_product_id → user_product_id` per bruker. Ingen dropp av `products` / `product_aliases`.
2. **006 (S04-A):** Kolonner på kvittering/linje for `date_precision`, `date_source`, `purchase_time`, `line_type`, `net_line_total`, `printed_unit_price`, `quantity_unit`, `price_basis`, `condition`. Eksisterende `unit_price` / `line_total` beholdes. Ukjente verdier settes til `unknown`, aldri gjettet enhet.
3. **007 (S05-A):** `receipt_revisions`, stabile linje-ID-er, `version` på kvittering. Bekreftede kvitteringer får revisjon 1 som gjeldende. `PUT /receipts/{id}/confirm` skriver fortsatt v1-form inntil klienten bytter.
4. **008 (S06-A):** `shopping_lists`, `shopping_list_items`, `mutations`, tombstones.
5. **009 (S09-A):** Auth-sesjoner (`refresh_sessions`, `password_reset_tokens`). Allerede levert.
6. **010 (S10-B):** `job_outbox` for OCR-jobber og `users.deleted_at` som slettingsgjerde. Eksisterende Celery-kø drains parallelt.
7. **011 (S09-C):** `account_deletions`, `exports`, retention-felter. Slettemarkør før fysisk sletting.

Hver migrering har `upgrade` og dokumentert `downgrade` eller forward-fix. Indekser: `(user_id, …)` på alle private tabeller, unik `(user_id, mutation_id, operation)`.

## Backfill-regler

- Ett `UserProduct` per `(user_id, product_id)` fra bekreftede linjer.
- `identity_status = inherited` der matchingen bare kommer fra globalt alias.
- Original `raw_product_name` kopieres til privat alias; andres tekst kopieres ikke.
- Prisobservasjoner pekes om via mappingtabell uten å endre beløp i rå linjer.
- Ukjent `purchase_date` forblir null. **Ikke** fyll inn `created_at`.

## Rollback

Ved feil: stopp v2-ruter, behold v1. Nye tabeller kan bli stående. Ikke slett mappingtabellen. Restore fra PostgreSQL-backup (S10-E, menneskeeid) må respektere slettemarkører.

## Verifikasjon

Frisk DB og oppgradering fra 004 testes i S10-A mot PostgreSQL. SQLite-tester er ikke bevis for låser, Decimal-presisjon i SQL eller samtidig migrering.
