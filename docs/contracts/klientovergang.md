# Klientovergang

Gjeldende Android (historikk, søk, `PUT /receipts/{id}/confirm`) skal fortsette å virke mot v1 mens v2 bygges.

## Hva som er stabilt

| Klientkall | Status |
|---|---|
| `POST /auth/register\|login\|google\|refresh`, `GET /auth/me` | Beholdes. Refresh-rotasjon innføres i S09-A uten å bryte body-feltet `refresh_token` |
| `POST /receipts`, `GET /receipts`, `GET /receipts/{id}`, retry, image, delete | Beholdes. Nye køtilstander mappes: v1 `FAILED` kan være `failed_permanent` eller `needs_action` i lokal modell |
| `PUT /receipts/{id}/confirm` | Beholdes. Skriver revisjon 1-ekvivalent og publiserer observasjoner med dagens (kjente) begrensninger inntil S05-A er i bruk |
| `GET /products/search`, `GET /products/{id}/my-prices`, `GET /stores` | Beholdes. Svar kan inneholde globale ID-er. Ny UI skal ikke bruke dem til handleliste |

## Hva ny kode skal kalle

Handleliste, mine varer, v2-pris, kladd/revisjon, sync, eksport og kontosletting: kun `/v2/...`.

Ny Android-modul speiler OpenAPI og fixtures. Ikke bland globalt `product_id` inn i `ShoppingListItem`.

## Feature-deteksjon

Hvis `/v2/shopping-lists` gir 404, skjul handleliste og vis eksisterende Hjem/Historikk/Søk. Dette er overgang, ikke varig gjestemodus.

## Testdekning

C00-fixtures er felles. Integrasjon mot levende backend er eget steg før ferdigmelding av hver Android-oppgave (se spesifikasjon §11).
