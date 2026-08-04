# Kvitteringsformater – analyse av testdata

Basert på 3 eksempelkvitteringer mottatt 2026-08-04.

## Felles mønstre (alle butikker)

| Felt | Format | Parser-notat |
|------|--------|--------------|
| Dato | `DD.MM.YY HH:MM` eller `DD MM YYYY HH:MM:SS` | Normaliser til ISO-8601 |
| Pris | Norsk desimal: `39,90` | Konverter til `Decimal` / `39.90` |
| MVA | 15 % (mat), 25 % (ikke-mat) | Lagre som metadata, ikke kritisk for MVP |
| Org.nr | `NNN NNN NNN` eller `NNNNNNNNN` | Brukes til butikk-gjenkjenning |
| Dokumenttype | «Salgskvittering» | Marker start på transaksjonsdata |

## Rema 1000

**Fil:** `testdata/receipts/rema1000-metro-senter.png`

### Butikk-gjenkjenning

```
REMA 1000                    ← logo/chain
REMA 1000 METRO SENTER       ← butikknavn
CHRISTIN DAGLIGVARE AS       ← juridisk enhet
933 454 517                  ← org.nr
```

**Detektor:** Regex `(?i)rema\s*1000` i header (første 15 linjer).

### Metadata

```
04.08.26 20:41    Kasse: 007    OperNr: 407
Kvitt: 137286     Serienr.: 134333
```

### Linjeformat

```
PRODUKTNAVN                    MVA%    PRIS
Q LETTMELK 1%                  15      31,40
NYPOTET LØSVEKT                15      31,25
  1,045kg x kr 29,90                   ← vekt-linje (under produkt)
```

**Parser-regler:**
- Produktlinje: tekst + MVA-prosent (15/25) + pris høyrejustert
- Vekt-linje: indentert, `(\d+[,.]?\d*)\s*kg\s*x\s*kr\s*(\d+[,.]\d{2})` – knytt til forrige produkt
- Ignorer etter `Sum N varer` (unntatt total)
- Ignorer `KORTINNEHAVERENS KVITTERING`-seksjon (duplikat betalingsinfo)

### Forventet output (7 varer)

| Produkt | Pris | Type |
|---------|------|------|
| Q LETTMELK 1% | 31,40 | fast |
| COTTAGE CH. MAGER | 26,90 | fast |
| YOGHURT | 8,80 | fast |
| BROKKOLI | 29,90 | fast |
| NYPOTET LØSVEKT | 31,25 | vekt (1,045 kg × 29,90) |
| AUBERGINE LØSVEKT | 23,83 | vekt (0,385 kg × 61,90) |
| BÆREPOSE 80% RESIR | 6,75 | fast (25 % MVA) |

**Total:** 158,83 | **Dato:** 2026-08-04 20:41

---

## Normal

**Fil:** `testdata/receipts/normal-triaden.png`

### Butikk-gjenkjenning

```
Normal                       ← logo i boks
Normal Oslo, Thon Senter Triaden
Organisasjonsnr: 917019738 MVA
```

**Detektor:** `(?i)^normal\b` eller org.nr `917019738`.

### Metadata

```
000000P378000953321    Ansatt Evy    Trans 953791
Dato 31.07.26 19:36
```

### Linjeformat

```
Beskrivelse                              Beløp
MALACO SNØRE JORDBÆR 94G                 16,00 B
SKITTLES CRAZY SOURS 152                 20,00 B
```

**Parser-regler:**
- Header: `Beskrivelse` / `Beløp`
- Produktlinje: navn + pris + valgfri MVA-bokstav (`B` = 15 %)
- Total: `I alt kr.` → 100,00
- Ignorer kontant/vekslepenger-linjer for produktliste
- Ignorer MVA-oppsummeringstabell

### Forventet output (6 varer)

| Produkt | Pris |
|---------|------|
| MALACO SNØRE JORDBÆR 94G | 16,00 |
| SKITTLES CRAZY SOURS 152 | 20,00 |
| SKITTLES FRUITS 152G | 20,00 |
| MILKA OREO 100G | 18,00 |
| SOUR PATCH WATERMELON 40 | 10,00 |
| NO REESE'S 2 PEANUT BUTT | 16,00 |

**Total:** 100,00 | **Dato:** 2026-07-31 19:36

---

## Europris

**Fil:** `testdata/receipts/europris-normal-triaden.png` (Europris-delen)

### Butikk-gjenkjenning

```
Europris                     ← logo
EP TRIADEN                   ← butikknavn (prefiks EP)
Orgnr: 987553014 MVA
```

**Detektor:** `(?i)europris` eller `(?i)^ep\s`.

### Metadata

```
Kasserer: 633008    Kasse: 102    Kvitt.nr: 398
31 07 2026 19:57:23
```

### Linjeformat

```
VARE                         MVA%    SUM
SUPERMIX SMÅGODT 220 G       15      39,90
```

**Parser-regler:**
- Header: `VARE` / `MVA%` / `SUM`
- Total: `Å BETALE` → 39,90
- Ignorer kontant/tilbake-linjer
- Ignorer returpolicy-footer og strekkode

### Forventet output (1 vare)

| Produkt | Pris |
|---------|------|
| SUPERMIX SMÅGODT 220 G | 39,90 |

**Total:** 39,90 | **Dato:** 2026-07-31 19:57:23

---

## Utfordringer for OCR

| Utfordring | Eksempel | Mitigering |
|------------|----------|------------|
| Termokvittering, lav kontrast | Alle tre | Kontrastforsterkning (OpenCV) |
| Foldede/bøyde kvitteringer | Normal | Perspektivkorreksjon |
| Forkortede produktnavn | `Q LETTMELK`, `COTTAGE CH. MAGER` | Behold rå tekst; normaliser senere |
| Vekt-linjer under produkt | Rema løsvekt | Tolk som child-linje av forrige item |
| To kvitteringer i ett bilde | europris-normal-triaden.png | Detekter flere kvitteringsregioner (senere) |
| Kortkvittering duplikat | Rema nederst | Stopp parsing ved «KORTINNEHAVERENS» |

## Produkt-normalisering (eksempler)

For «billigst for meg»-matching:

| Rå tekst | Canonical |
|----------|-----------|
| `Q LETTMELK 1%` | `Q lettmelk 1% 1l` (antatt) |
| `SUPERMIX SMÅGODT 220 G` | `supermix smågodt 220g` |
| `MALACO SNØRE JORDBÆR 94G` | `malaco snøre jordbær 94g` |

Normalisering: lowercase → fjern spesialtegn → ekstraher vekt/volum fra suffix (`220 G`, `94G`, `1%`).

## Regresjonstester (planlagt)

Hver kvittering får en `expected.json` med ground truth:

```json
{
  "store_chain": "rema1000",
  "store_name": "REMA 1000 METRO SENTER",
  "purchase_date": "2026-08-04T20:41:00",
  "total": 158.83,
  "items": [
    { "raw_name": "Q LETTMELK 1%", "price": 31.40, "quantity": 1 }
  ]
}
```
