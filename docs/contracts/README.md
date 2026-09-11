# C00 — felles kontrakter (P0)

Låst grunnlag for Android og backend. Eksisterende v1-ruter (`/auth`, `/receipts`, `/products`, `/stores`) beholdes. Nye og endrede domener ligger under `/v2`.

| Dokument | Innhold |
|---|---|
| [ADR-001 privat produktidentitet](ADR-001-privat-produktidentitet.md) | Hvorfor `UserProduct` erstatter global brukerinnsendt matching |
| [Datamodell](datamodell.md) | Entiteter, eierskap, versjoner |
| [Penger og avrunding](penger-og-avrunding.md) | Decimal-strenger, presisjon, ROUND_HALF_UP |
| [Feil og offline](feil-og-offline.md) | Feilformat, idempotens, konflikter |
| [Migrasjonsplan](migrasjonsplan.md) | Additiv overgang, ingen destruktiv P0-migrering |
| [Klientovergang](klientovergang.md) | Hva gjeldende app kan kalle mens v2 rulles ut |
| [openapi-v2.json](openapi-v2.json) | Skjemaer og ruter |
| [fixtures/](fixtures/) | Gylne eksempler begge klienter bygger tester mot |

Kanonisk implementasjon av avrunding: `backend/app/domain/money.py` og `backend/app/domain/units.py`. Android speiler med `BigDecimal` og samme kvanta.

Verifikasjon: `cd backend && .venv/bin/python -m pytest tests/contracts/test_c00_contracts.py -q`
