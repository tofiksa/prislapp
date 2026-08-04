# Eksempelkvitteringer

Anonymiserte testkvitteringer for OCR- og parser-utvikling.

| Fil | Butikk | Notater |
|-----|--------|---------|
| `rema1000-metro-senter.png` | Rema 1000 | 7 varer, løsvekt, MVA 15/25 %, kortbetaling |
| `normal-triaden.png` | Normal | 6 varer, kontant, enkel tabell |
| `europris-normal-triaden.png` | Europris (+ delvis Normal) | Europris: 1 vare; høyre halvdel avskåret |

## Parser-prioritet (MVP)

1. **Rema 1000** – dagligvare, mest relevant for prissammenligning
2. **Normal** – enkel struktur, god for generisk parser-test
3. **Europris** – variant layout, færre dagligvarer

Se `docs/superpowers/specs/2026-08-04-receipt-formats.md` for detaljert formatanalyse.
