# Prislapp – UI-struktur

**Status:** Klar for implementasjon  
**Dato:** 2026-09-10  
**Versjon:** 1.0  
**Grunnlag:** UX-gjennomgang 2026-09-10 og systemdesign 2026-08-04

## Mål

Gjøre den eksisterende Android-appen lesbar som et produkt, uten å endre forretningsregler, OCR eller API-kontrakter utover ett nytt bilde-endepunkt.

Brukeren skal på ett blikk skjønne: ta bilde av kvittering, rett det OCR leste, se hvor *jeg* har handlet billigst.

## Ikke i scope

- Nytt fargepalett, illustrasjoner, animasjoner, dark theme
- Nye produktfunksjoner (push, deling, flere kvitteringer i ett bilde, kontoinnstillinger-skjerm utover logg ut)
- Endring av Room-skjema, WorkManager-flyt, JWT, OCR-pipeline
- Backend-endringer utenom `GET /receipts/{id}/image`

## Låste beslutninger

| Tema | Beslutning |
|------|------------|
| Navigasjon innlogget | Material 3 `NavigationBar` med tre destinasjoner: Hjem, Historikk, Søk. Kamera er FAB kun på Hjem. |
| Tilbake | `IconButton` med `Icons.AutoMirrored.Filled.ArrowBack` og `contentDescription` = streng `back`. Ikke tekstknappen «Tilbake». |
| Kjerne-CTA | Én fylt handling for å ta bilde. Aldri `OutlinedButton` som likeverdig med kjernehandlingen. |
| Logg ut | Overflow-meny (`MoreVert`, `contentDescription` = `account_menu`) i Hjem-`TopAppBar`. Fjern fylt Logg ut-knapp fra innholdet. |
| Lister | `ReceiptRow` (klikkbar rad), aldri `OutlinedButton` som listeelement. |
| Status | Menneskelig norsk via `receiptStatusLabel()`. Aldri vis `PENDING`, `PROCESSING`, `READY_FOR_REVIEW` o.l. i UI. |
| Kø-ID | Ikke vis `#12` eller intern `localId` i UI. |
| Tomtilstand | Egen `EmptyState` med tittel + brødtekst. Ikke en tom `LazyColumn`. |
| Gjennomgang | Originalbildet øverst. Dato via `DatePickerDialog`. Rå OCR skjult bak ekspander. |
| Søk | Live-søk, 300 ms debounce, minst 2 tegn. Ingen egen Søk-knapp. |
| Tema | Behold `GreenPrimary` / `GreenSecondary`. Ingen ny design-token-fil. |
| Ikoner | `androidx.compose.material:material-icons-extended` fra Compose BOM. |
| Bilder i review | Coil 2.7 + eksisterende OkHttp-klient (auth). Lokal fil hvis den finnes, ellers `GET /receipts/{id}/image`. |

## Informasjonsarkitektur

```
Uinnlogget:  Login ⇄ Register
Innlogget skall:
  [Hjem]     siste + kø + FAB «Ta bilde»
  [Historikk] bekreftede kvitteringer + filter
  [Søk]      produktsøk → Billigst for meg
Overlegg (ikke i bunnnav):
  Kamera → Behandling → Gjennomgang
```

Hjem er ikke lenger en meny. Historikk og Søk flyttes til bunnnav. Kamera, behandling og gjennomgang forblir stakk over Hjem.

## Delt visningsmodell

### Statuskopi

Fil: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptStatusCopy.kt`

```kotlin
fun receiptStatusLabel(status: String): String
```

Mapper (eksakt):

| Intern status | Norsk i UI | Streng-ressurs |
|---------------|------------|----------------|
| `PENDING` | Venter på opplasting | `status_pending` |
| `UPLOADING` | Laster opp… | `status_uploading` |
| `UPLOADED` | Lastet opp | `status_uploaded` |
| `PROCESSING` | Leser kvitteringen… | `status_processing` |
| `READY_FOR_REVIEW` | Klar til gjennomgang | `status_ready` |
| `FAILED` | Kunne ikke leses | `status_failed` |
| `CONFIRMED` | Bekreftet | `status_confirmed` |
| ukjent | vis status uendret | — |

`receiptStatusLabel` tar `Context` eller ferdig oppslåtte strenger via `@Composable` wrapper:

```kotlin
@Composable
fun receiptStatusLabel(status: String): String
```

Implementer som composable som leser `stringResource`. For JVM-test: ren funksjon

```kotlin
fun receiptStatusLabelRes(status: String): Int
```

som returnerer `R.string.*` (ukjent → `R.string.status_unknown` med format `%1$s`).

### Kvitteringsrad

Fil: `android/app/src/main/java/no/prislapp/ui/components/ReceiptRow.kt`

```kotlin
@Composable
fun ReceiptRow(
    title: String,
    subtitle: String,
    statusLabel: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
)
```

- Hele raden er `clickable`, 16.dp vertikal padding, skillelinje under.
- `title`: butikknavn, eller `unknown_store` hvis tom.
- `subtitle`: `dd.MM.yyyy · 412,50 kr` — utelat dato og/eller beløp som mangler. Ikke vis `?`.
- `statusLabel`: vises som `bodySmall` i `onSurfaceVariant` til høyre, eller under subtitle hvis plassen er trang. På Hjem-kø er status primær (subtitle kan være tom).
- Ikke vis intern id.

Hjelpere (samme fil eller `ReceiptRowFormat.kt`):

```kotlin
fun formatReceiptSubtitle(purchaseDateIso: String?, total: java.math.BigDecimal?): String
```

Dato: `yyyy-MM-dd` eller ISO-instant → `dd.MM.yyyy` i `Europe/Oslo`. Total: norsk desimal med `kr` (`25,90 kr`). Tom streng hvis begge mangler.

### Tomtilstand

Fil: `android/app/src/main/java/no/prislapp/ui/components/EmptyState.kt`

```kotlin
@Composable
fun EmptyState(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
)
```

Sentrert kolonne, `titleMedium` + `bodyMedium` i `onSurfaceVariant`. Ingen knapp inne i komponenten (CTA ligger utenfor: FAB).

### Toppbar med tilbake

Fil: `android/app/src/main/java/no/prislapp/ui/components/PrislappTopBar.kt`

```kotlin
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrislappTopBar(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
)
```

Hvis `onBack != null`: `IconButton` + `ArrowBack` + `contentDescription` fra `R.string.back`.

## Skjerm for skjerm

### Login / registrer

Uendret flyt. Ingen krav i denne specen utover at de fortsatt virker.

### Hjem

**Toppbar:** tittel `home_title` («Prislapp»). Action: `MoreVert` → `DropdownMenu` med ett punkt `logout`.

**Innhold:**

1. Hvis kø ikke tom: seksjonstittel `upload_queue`, deretter `ReceiptRow` per pending. Title = `queued_receipt` («Kvittering»). Subtitle tom. Status = `receiptStatusLabel(status)`. Klikk: samme navigasjon som i dag (`onOpenReceipt` / `onOpenPending`).
2. Hvis serverkvitteringer ikke tom: seksjonstittel `recent_receipts`, `ReceiptRow` med butikk / subtitle / status. Klikk: `onOpenReceipt`.
3. Hvis kø tom OG serverliste tom OG ikke lasting: `EmptyState` med `home_empty_title` + `home_empty_body`.
4. Feil: `error`-farget tekst som i dag.
5. Ingen «Velkommen!». Ingen Historikk-/Produktsøk-knapper etter bunnnav er på plass (midlertidig: se implementasjonsplan task 3 vs 4).
6. Ingen Logg ut i listen.

**FAB:** `FloatingActionButton` med `Icons.Default.PhotoCamera`, `contentDescription` = `capture_receipt`. `onClick` = `onCaptureReceipt`. Alltid synlig på Hjem når innlogget.

### Historikk

- `PrislappTopBar` med tilbake inntil bunnnav (etter bunnnav: **ingen** tilbake, destinasjonen er rot i skallet).
- Dato-filter uendret funksjonelt (`DatePickerDialog`).
- Butikkfilter: `FlowRow` med `FilterChip`, `spacedBy(8.dp)`. Ikke `Column` av chips.
- Kvitteringer: `ReceiptRow`. Status-label utelates her (listen er bekreftede). Title = butikk, subtitle = dato · total.
- Tom: `EmptyState` `history_empty_title` / `history_empty_body`.
- `load_more` forblir knapp nederst.

### Produktsøk (Søk-tab)

- SøkeFelt øverst, `label` = `search_products`. Ingen Søk-knapp.
- `updateQuery` starter 300 ms debounce. `query.trim().length < 2` → tøm resultater, `hasSearched = false`, ikke kall API.
- Resultater: klikkbar rad med `canonical_name` (kan gjenbruke `ReceiptRow` med tom subtitle/status, eller en `ListItem`).
- Tom etter søk: eksisterende `no_products`.
- Før første søk: ingen tomtilstand-tekst.

### Billigst for meg

Rekkefølge, visuell vekt:

1. Produktnavn `titleLarge`
2. Hero: hvis `cheapest != null`, `Card` med `cheapest_price` som `headlineSmall` (butikk + pris). Under: observasjonsdato `dd.MM.yyyy`.
3. Forklaring `price_per_unit` som `bodySmall`
4. Seksjon `latest_store_prices`: én linje per butikk `Navn · 12,50 kr · dd.MM.yyyy`
5. Seksjon `all_observations` med lavere vekt (`titleSmall` + `bodyMedium`), samme linjeformat

Ingen `OutlinedButton`. Hvis `cheapest == null`: vis produktnavn + `no_price_observations` («Ingen prisobservasjoner ennå»).

### Kamera

- Fullskjerm preview som i dag. Pipeline uendret.
- Veiledning `camera_guidance` øverst, hvit tekst, 16.dp.
- Lukker: fylt sirkel 72.dp nederst i midten, hvit kamera-ikon, `contentDescription` = `capture_button`. Ikke Material `Button` med tekst.
- Galleri: `IconButton` nederst til venstre, `Icons.Default.PhotoLibrary`, `contentDescription` = `pick_from_gallery`.
- Tilbake via `PrislappTopBar`.
- Tillatelse / feil uendret.

### Behandling

- Tittel: `processing_title` = «Leser kvitteringen»
- Spinner når `isPolling`
- Brødtekst avhenger av status, aldri `Status: PROCESSING`:
  - `PENDING` / `UPLOADING` / `UPLOADED`: `processing_body_upload`
  - `PROCESSING`: `processing_body_ocr`
  - `FAILED` eller error: `processing_body_failed` + `retry`-knapp
- Ukjent/andre: `receiptStatusLabel(status)` som fallback

### Gjennomgang

Rekkefølge i `LazyColumn`:

1. Bilde: høyde 180.dp, `ContentScale.Crop`, hele bredden. Kilde: lokal `File` hvis `imagePath` finnes og filen eksisterer, ellers Coil mot `GET {API_BASE_URL}receipts/{id}/image`. Ved 410/feil: vis `image_unavailable` og fortsett uten bilde. Ikke blokker skjemaet.
2. Kjøpsdato: `OutlinedTextField` `readOnly = true` (også når ikke readOnly-kvittering). Klikk åpner samme `DatePickerDialog`-mønster som Historikk. Verdien vises `dd.MM.yyyy`. Lagring/bekreftelse uendret (`dd.MM.uuuu` → ISO i ViewModel).
3. Butikk, total: uendret felt.
4. Varer: hver linje i `Card` (eller `OutlinedCard`) med navn full bredde, deretter rad antall / enhetspris / linjepris. `remove_item` som `TextButton` i kortet, ikke `OutlinedButton`.
5. `add_item` som `TextButton`.
6. `confirm_receipt` fylt, full bredde, kun når ikke readOnly.
7. `ocr_text` bak `TextButton` «Vis gjenkjent tekst» / «Skjul gjenkjent tekst». Standard: skjult.
8. `delete_receipt` som `TextButton` i error-farge nederst. Dialogtekst uendret. Avbryt-streng: bruk `select_date_cancel` inntil egen `cancel` finnes — **legg til** `R.string.cancel` = «Avbryt» og bruk den i slettedialogen.

Bekreftelse og sletting: samme ViewModel-kontrakt som i dag (`isConfirmed`, `isDeleted`).

## API: kvitteringsbilde

`GET /receipts/{receipt_id}/image`

| Tilstand | HTTP | Body |
|----------|------|------|
| Innlogget eier, bilde finnes og ikke utløpt | 200 | Bildebytes, `Content-Type` `image/jpeg` (eller lagret type) |
| Ikke innlogget | 401 | eksisterende auth-feil |
| Kvittering finnes ikke / annen bruker | 404 | `{"detail":"Receipt not found"}` |
| `image_path` tom eller `image_expires_at` passert | 410 | `{"detail":"Original image expired"}` |

Eierskap via `ReceiptService.get_receipt_for_user` som øvrige GET. Last bytes via `StorageService.download_receipt`. Ingen signert MinIO-URL i klienten.

Android Retrofit:

```kotlin
@GET("receipts/{id}/image")
@Streaming
suspend fun getReceiptImage(@Path("id") id: String): ResponseBody
```

Coil skal bruke **samme** `OkHttpClient` som Retrofit (auth + refresh). Ikke last bildet uten Authorization.

Lokal fil: `PendingReceiptDao.getByServerReceiptId(receiptId)` → `File(imagePath).exists()`.

## Streng-ressurser (nye / endrede)

Legg alle i `android/app/src/main/res/values/strings.xml`. Ikke hardkod norsk i composables (unntak: eksisterende register-validering kan bli liggende).

| Name | Verdi |
|------|--------|
| `status_pending` | Venter på opplasting |
| `status_uploading` | Laster opp… |
| `status_uploaded` | Lastet opp |
| `status_processing` | Leser kvitteringen… |
| `status_ready` | Klar til gjennomgang |
| `status_failed` | Kunne ikke leses |
| `status_confirmed` | Bekreftet |
| `status_unknown` | %1$s |
| `queued_receipt` | Kvittering |
| `home_empty_title` | Ingen kvitteringer ennå |
| `home_empty_body` | Ta bilde av en handlelapp for å lagre priser og se hvor du har handlet billigst. |
| `history_empty_title` | Ingen kvitteringer |
| `history_empty_body` | Bekreftede kvitteringer vises her. |
| `nav_home` | Hjem |
| `nav_history` | Historikk |
| `nav_search` | Søk |
| `account_menu` | Konto |
| `processing_title` | Leser kvitteringen |
| `processing_body_upload` | Kvitteringen lastes opp. Du kan lukke denne skjermen — vi fortsetter i bakgrunnen. |
| `processing_body_ocr` | Vi henter butikk, dato og varer. Dette tar vanligvis under et minutt. |
| `processing_body_failed` | Vi fikk ikke lest kvitteringen. Prøv igjen, eller ta et nytt bilde med bedre lys. |
| `image_unavailable` | Kvitteringsbildet er ikke tilgjengelig. |
| `show_ocr` | Vis gjenkjent tekst |
| `hide_ocr` | Skjul gjenkjent tekst |
| `cancel` | Avbryt |
| `no_price_observations` | Ingen prisobservasjoner ennå. |

Endre: `processing_status` skal **ikke lenger brukes i UI**. Behold nøkkelen eller slett den når siste kall er borte.

## Testkrav

- JVM: mapper, debounce i `ProductSearchViewModel`, `formatReceiptSubtitle`, Home viser ikke lenger logout som innhold (hvis det testes), review dato via picker oppdaterer `purchaseDate` i ViewModel (eksisterende confirm-test skal fortsatt passere).
- Backend: 200 for eier, 404 for annen bruker, 410 når path tom / utløpt, 401 uten token.
- Instrumentering `AuthNavigationTest`: tilpass til bunnnav-etiketter, overflow-logout, live-søk uten Søk-knapp, `contentDescription` for tilbake. Behold opt-in mot `10.0.2.2:18000`.

## Akseptansekriterier

En person som aldri har sett kodebasen skal kunne:

1. Etter login se FAB som tydeligste handling, ikke Logg ut.
2. Skille kø og siste kvitteringer som rader med norsk status, uten enum-strenger.
3. Navigere Hjem / Historikk / Søk via bunnen.
4. På gjennomgang se (eller tydelig manglende) kvitteringsbilde og rette linjer mot det.
5. Søke ved å skrive, og se billigste butikk som første svar på prisskjermen.

## Implementasjon

Arbeidsliste for agenter: [2026-09-10-ui-struktur.md](../plans/2026-09-10-ui-struktur.md)
