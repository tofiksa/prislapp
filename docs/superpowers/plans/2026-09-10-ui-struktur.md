# UI-struktur Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Omstrukturere Android-UI slik at kjernehandlingen, listene og «billigst for meg» leses som et produkt, uten å endre OCR eller forretningsregler.

**Architecture:** Delt visningslag (`ReceiptStatusCopy`, `ReceiptRow`, `EmptyState`, `PrislappTopBar`) først. Deretter skjerm for skjerm. Ett nytt backend-endepunkt `GET /receipts/{id}/image`. Innlogget skall får `NavigationBar` + FAB. Eksisterende ViewModel-kontrakter (`isConfirmed`, kø, filter) beholdes.

**Tech Stack:** Kotlin, Jetpack Compose Material 3, Hilt, Retrofit/OkHttp, Coil 2.7, FastAPI, pytest, JUnit/MockK.

**Spec:** `docs/superpowers/specs/2026-09-10-ui-struktur-design.md` er kilde til kopi, IA og akseptanse. Ikke finn på annen tekst eller navigasjon.

## Global Constraints

- Norsk UI-kopi kun via `strings.xml` (unntak: eksisterende hardkodet register-validering).
- Aldri vis interne statuskoder (`PENDING`, `PROCESSING`, `READY_FOR_REVIEW`, …) i synlig UI.
- Ikke vis intern kø-id (`#12`).
- Lister er rader, ikke `OutlinedButton`.
- Behold `GreenPrimary` / `GreenSecondary`. Ingen dark theme, ingen ny token-fil.
- Ikke endre Room-skjema, WorkManager, JWT, OCR, parser eller bekreftelses-API.
- Eneste backend-endring: `GET /receipts/{id}/image`.
- Ikoner: `androidx.compose.material:material-icons-extended`.
- Coil 2.7.0 (`coil-compose` + bruk eksisterende OkHttpClient).
- `contentDescription` for tilbake = `R.string.back`, overflow = `R.string.account_menu`, FAB = `R.string.capture_receipt`.
- Ikke commit hemmeligheter. Commit per task med conventional commits (`feat(ui):` / `test:` / `feat(api):`).
- Kjør tester som står i tasken. Ikke skip failing tests.

## File structure

| Fil | Ansvar |
|-----|--------|
| `android/.../ui/receipt/ReceiptStatusCopy.kt` | Status → `R.string` |
| `android/.../ui/components/ReceiptRow.kt` | Klikkbar kvitteringsrad + `formatReceiptSubtitle` |
| `android/.../ui/components/EmptyState.kt` | Tomtilstand |
| `android/.../ui/components/PrislappTopBar.kt` | Toppbar ± tilbake ± actions |
| `android/.../ui/navigation/PrislappNavHost.kt` | Ruter + bunnnav-skall |
| `android/.../ui/home/HomeScreen.kt` | Hjem uten meny-knapper |
| `android/.../ui/history/HistoryScreen.kt` | Filter + rader |
| `android/.../ui/product/ProductScreens.kt` | Live-søk + pris-hero |
| `android/.../ui/receipt/ReceiptScreens.kt` | Behandling + gjennomgang |
| `android/.../ui/camera/CameraScreen.kt` | Lukker + galleri-ikon |
| `android/app/src/main/res/values/strings.xml` | All ny kopi |
| `backend/app/routers/receipts.py` | Image GET |
| `android/.../data/remote/PrislappApi.kt` | `getReceiptImage` |
| `android/.../di/NetworkModule.kt` | Coil `ImageLoader` med samme OkHttpClient |

## Delegation order

Kjør **en task per agent**. Ikke start en task før avhengighetene er merget.

```
Task 1
  └─ Task 2
       ├─ Task 3 ─┐
       │          └─ Task 4
       ├─ Task 6
       ├─ Task 7
       └─ Task 10 (etter Task 5)
  Task 5  (kan parallelt med 1–3; 10 venter på 5)
  Task 8  (uavhengig)
  Task 9  (uavhengig)
  Task 11 (uavhengig)
  Task 12 (sist, etter 4, 8, 10)
```

---

### Task 1: Statuskopi og strenger

**Files:**
- Create: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptStatusCopy.kt`
- Create: `android/app/src/test/java/no/prislapp/ui/receipt/ReceiptStatusCopyTest.kt`
- Modify: `android/app/src/main/res/values/strings.xml`

**Interfaces:**
- Consumes: `PendingReceiptEntity.STATUS_*` og serverstatus-strenger (samme verdier).
- Produces:

```kotlin
package no.prislapp.ui.receipt

fun receiptStatusLabelRes(status: String): Int
```

Mapper:

- `PENDING` → `R.string.status_pending`
- `UPLOADING` → `R.string.status_uploading`
- `UPLOADED` → `R.string.status_uploaded`
- `PROCESSING` → `R.string.status_processing`
- `READY_FOR_REVIEW` → `R.string.status_ready`
- `FAILED` → `R.string.status_failed`
- `CONFIRMED` → `R.string.status_confirmed`
- ellers → `R.string.status_unknown`

Composable-wrapper i samme fil:

```kotlin
@Composable
fun receiptStatusLabel(status: String): String {
    val res = receiptStatusLabelRes(status)
    return if (res == R.string.status_unknown) {
        stringResource(res, status)
    } else {
        stringResource(res)
    }
}
```

**Agent prompt (lim inn som hele oppgaven):**

Les `docs/superpowers/specs/2026-09-10-ui-struktur-design.md` seksjon «Statuskopi» og «Streng-ressurser». Implementer kun Task 1. Ikke rør skjermer.

- [ ] **Step 1: Skriv failing test**

```kotlin
package no.prislapp.ui.receipt

import no.prislapp.R
import org.junit.Assert.assertEquals
import org.junit.Test

class ReceiptStatusCopyTest {
    @Test
    fun mapsKnownStatuses() {
        assertEquals(R.string.status_pending, receiptStatusLabelRes("PENDING"))
        assertEquals(R.string.status_uploading, receiptStatusLabelRes("UPLOADING"))
        assertEquals(R.string.status_uploaded, receiptStatusLabelRes("UPLOADED"))
        assertEquals(R.string.status_processing, receiptStatusLabelRes("PROCESSING"))
        assertEquals(R.string.status_ready, receiptStatusLabelRes("READY_FOR_REVIEW"))
        assertEquals(R.string.status_failed, receiptStatusLabelRes("FAILED"))
        assertEquals(R.string.status_confirmed, receiptStatusLabelRes("CONFIRMED"))
    }

    @Test
    fun unknownStatusUsesFallbackResource() {
        assertEquals(R.string.status_unknown, receiptStatusLabelRes("SOMETHING_ELSE"))
    }
}
```

- [ ] **Step 2: Kjør test, forvent FAIL** (symbol ikke funnet)

```bash
cd android && ./gradlew :app:testDebugUnitTest --tests no.prislapp.ui.receipt.ReceiptStatusCopyTest
```

- [ ] **Step 3: Legg inn strengene fra spec-tabellen** i `strings.xml` (alle `status_*`, pluss de andre nye nøklene i specen så senere tasks ikke konflikter på samme fil). Inkluder hele tabellen «Streng-ressurser» i denne tasken.

- [ ] **Step 4: Implementer `ReceiptStatusCopy.kt` som over.**

- [ ] **Step 5: Kjør testen igjen. Forvent PASS.**

- [ ] **Step 6: Commit**

```bash
git add android/app/src/main/java/no/prislapp/ui/receipt/ReceiptStatusCopy.kt \
  android/app/src/test/java/no/prislapp/ui/receipt/ReceiptStatusCopyTest.kt \
  android/app/src/main/res/values/strings.xml
git commit -m "$(cat <<'EOF'
feat(ui): map receipt statuses to Norwegian copy

EOF
)"
```

**Done when:** Testen over er grønn. Ingen skjerm endret. Alle nye `R.string.*` fra spec-tabellen finnes.

---

### Task 2: Delt rad, tomtilstand, toppbar

**Depends on:** Task 1 (strenger finnes).

**Files:**
- Create: `android/app/src/main/java/no/prislapp/ui/components/ReceiptRow.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/components/EmptyState.kt`
- Create: `android/app/src/main/java/no/prislapp/ui/components/PrislappTopBar.kt`
- Create: `android/app/src/test/java/no/prislapp/ui/components/ReceiptRowFormatTest.kt`
- Modify: `android/gradle/libs.versions.toml` — legg til icons-extended hvis den ikke finnes som BOM-library
- Modify: `android/app/build.gradle.kts` — `implementation("androidx.compose.material:material-icons-extended")` på Compose BOM

**Interfaces:**
- Produces:

```kotlin
fun formatReceiptSubtitle(purchaseDateIso: String?, total: java.math.BigDecimal?): String

@Composable
fun ReceiptRow(
    title: String,
    subtitle: String,
    statusLabel: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
)

@Composable
fun EmptyState(title: String, body: String, modifier: Modifier = Modifier)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrislappTopBar(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit = {},
)
```

`formatReceiptSubtitle`-regler:

- Parse `purchaseDateIso`: hvis den starter med 10 siffer-dato `yyyy-MM-dd`, bruk den; ellers parse `OffsetDateTime` og konverter til `Europe/Oslo` `LocalDate`. Format `dd.MM.yyyy`.
- Total: `toPlainString().replace('.', ',')` + `" kr"`.
- Begge: `"11.08.2026 · 25,90 kr"`.
- Bare dato: `"11.08.2026"`.
- Bare total: `"25,90 kr"`.
- Ingen: `""`.

`ReceiptRow`: `Column` med title `titleMedium`, subtitle `bodySmall` `onSurfaceVariant` hvis ikke blank, status til høyre (`bodySmall`) hvis ikke null/blank. Hele raden `clickable`. `PaddingValues(vertical = 12.dp)`. `HorizontalDivider` under.

`PrislappTopBar`: `TopAppBar`. Hvis `onBack != null`, `navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.back)) } }`.

- [ ] **Step 1: Failing test for formatter**

```kotlin
package no.prislapp.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class ReceiptRowFormatTest {
    @Test
    fun formatsDateAndTotal() {
        assertEquals(
            "11.08.2026 · 25,90 kr",
            formatReceiptSubtitle("2026-08-11T10:00:00Z", BigDecimal("25.90")),
        )
    }

    @Test
    fun omitsMissingParts() {
        assertEquals("", formatReceiptSubtitle(null, null))
        assertEquals("25,90 kr", formatReceiptSubtitle(null, BigDecimal("25.90")))
    }
}
```

- [ ] **Step 2: Kjør, forvent FAIL. Implementer. Kjør PASS.**

```bash
cd android && ./gradlew :app:testDebugUnitTest --tests no.prislapp.ui.components.ReceiptRowFormatTest
```

- [ ] **Step 3: Commit** `feat(ui): add shared receipt row and top bar`

**Done when:** Formatter-tester grønne. Tre komponentfiler finnes. Icons-extended kompilerer. Ingen skjerm wired ennå.

---

### Task 3: Hjem – hierarki, rader, overflow-logout, tomtilstand

**Depends on:** Task 1, Task 2.

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/home/HomeScreen.kt`
- Modify: `android/app/src/androidTest/java/no/prislapp/AuthNavigationTest.kt` (logout via meny)

**Behold inntil Task 4:** `OutlinedButton`/`TextButton` til Historikk og Produktsøk, ellers forsvinner navigasjon. Restyl dem som `TextButton`, ikke likeverdig med capture.

**Endre:**

- Fjern `R.string.welcome`.
- Fjern fylt `Button` logout fra listen.
- `TopAppBar` via `PrislappTopBar` med `actions`: `IconButton` `Icons.Default.MoreVert` `contentDescription = stringResource(R.string.account_menu)`. `DropdownMenu` med `DropdownMenuItem` tekst `stringResource(R.string.logout)` `onClick = onLogout`.
- Primær capture: `FloatingActionButton` i `Scaffold.floatingActionButton`, ikon `Icons.Default.PhotoCamera`, `contentDescription = capture_receipt`. Fjern outlined «Ta bilde av kvittering» fra listen.
- Kø: `ReceiptRow(title = stringResource(R.string.queued_receipt), subtitle = "", statusLabel = receiptStatusLabel(pending.status), onClick = …)`. Samme klikklogikk som i dag.
- Serverliste: `ReceiptRow(title = receipt.store?.name ?: stringResource(R.string.unknown_store), subtitle = formatReceiptSubtitle(receipt.purchase_date, receipt.total), statusLabel = receiptStatusLabel(receipt.status), onClick = { onOpenReceipt(receipt.id) })`.
- Tom: hvis `!isLoading && pending.isEmpty() && serverReceipts.isEmpty()` vis `EmptyState(home_empty_title, home_empty_body)`.
- Ikke vis intern id.

**AuthNavigationTest:** Etter login, vent på `contentDescription` «Konto» (norsk verdi av `account_menu`) i stedet for synlig «Logg ut». Før logout: `onNodeWithContentDescription("Konto").performClick()` deretter `onNodeWithText("Logg ut").performClick()`. Historikk/Produktsøk-klikk uendret i denne tasken.

- [ ] Implementer HomeScreen som over.
- [ ] Oppdater instrumenteringstestens logout-del.
- [ ] `./gradlew :app:testDebugUnitTest :app:lintDebug`
- [ ] Commit `feat(ui): make capture the primary home action`

**Done when:** Hjem har FAB + overflow logout + rader. Ingen enum-status i Hjem. Historikk/søk fortsatt nåbare via tekstknapper.

---

### Task 4: Innlogget skall med bunnnav

**Depends on:** Task 3.

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/navigation/Routes.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/navigation/PrislappNavHost.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/home/HomeScreen.kt` — fjern Historikk- og Produktsøk-knappene og tilhørende parametere
- Modify: `android/app/src/main/java/no/prislapp/ui/history/HistoryScreen.kt` — `onBack` blir optional/ubrukt i tab (ikke vis tilbake)
- Modify: `android/app/src/main/java/no/prislapp/ui/product/ProductScreens.kt` — `ProductSearchScreen` uten tilbake når den er tab
- Modify: `android/app/src/androidTest/java/no/prislapp/AuthNavigationTest.kt`

**Navigasjon:**

Behold `Routes.HOME`, `HISTORY`, `PRODUCT_SEARCH` som nå. I `NavHost` for innlogget tilstand: wrapp innhold i et `Scaffold` kun når current destination er en av de tre tab-rutene.

```kotlin
val tabRoutes = setOf(Routes.HOME, Routes.HISTORY, Routes.PRODUCT_SEARCH)
```

`NavigationBar` med tre `NavigationBarItem`:

| Route | Ikon | Label |
|-------|------|-------|
| HOME | `Icons.Default.Home` | `nav_home` |
| HISTORY | `Icons.Default.ReceiptLong` | `nav_history` |
| PRODUCT_SEARCH | `Icons.Default.Search` | `nav_search` |

Klikk: `navController.navigate(route) { popUpTo(Routes.HOME) { saveState = true }; launchSingleTop = true; restoreState = true }`.

Kamera, processing, review, product prices: **ingen** bunnnav. De har `PrislappTopBar` med tilbake som i dag.

FAB blir i `HomeScreen` (Task 3). Ytre skall-`Scaffold` skal **ikke** ha `floatingActionButton`. Resultat: nøyaktig én FAB, kun på Hjem.

Fjern `onOpenHistory` og `onOpenProductSearch` fra `HomeScreen`.

History og ProductSearch som tab: `PrislappTopBar(title, onBack = null)`.

Product prices: behold tilbake.

**AuthNavigationTest:**

- Etter login: `onNodeWithText("Historikk").performClick()` treffer bunnnav-label (ikke hjem-knapp).
- Ikke klikk «Tilbake» mellom Historikk og Søk. Gå `onNodeWithText("Søk").performClick()` (nav_search).
- Live-søk kan fortsatt ha Søk-knapp til Task 8; ikke fjern den her.
- Logout fortsatt via Konto-meny.

- [ ] Implementer skallet.
- [ ] Oppdater instrumenteringstest.
- [ ] `./gradlew :app:assembleDebug :app:testDebugUnitTest`
- [ ] Commit `feat(ui): add home history search bottom navigation`

**Done when:** Tre tabber, én FAB på hjem, overlegg uten bunnnav, hjem uten historikk/søk-knapper.

---

### Task 5: Kvitteringsbilde i gjennomgang

**Depends on:** ingen UI-tasks. Kan parallelt med 1–4. Task 10 venter på denne.

**Files:**
- Modify: `backend/app/routers/receipts.py`
- Modify: `backend/app/services/receipt_service.py` (kun hvis du trenger en liten `download`-hjelper; ellers kall storage fra router)
- Create or modify: `backend/tests/test_receipt_image.py` (ny fil foretrukket)
- Modify: `android/gradle/libs.versions.toml` + `android/app/build.gradle.kts` — Coil
- Modify: `android/app/src/main/java/no/prislapp/PrislappApplication.kt` — `Coil.setImageLoader` etter `super.onCreate()`
- Modify: `android/app/src/main/java/no/prislapp/data/remote/PrislappApi.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptViewModels.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptScreens.kt` (kun bildeblokk øverst; ikke skriv om resten av skjemaet)
- Modify: `android/app/src/test/java/no/prislapp/ui/receipt/ReceiptReviewViewModelTest.kt`

**Backend:**

```python
@router.get("/{receipt_id}/image")
async def get_receipt_image(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

1. `receipt = await ReceiptService(db).get_receipt_for_user(receipt_id, current_user.id)`
2. Hvis None → 404 `Receipt not found`
3. Normaliser `image_expires_at` til UTC som i `retry_receipt`. Hvis ikke `image_path` eller utløpt → 410 `Original image expired`
4. `data = await run_in_threadpool(StorageService().download_receipt, receipt.image_path)`
5. Returner `Response(content=data, media_type="image/jpeg")`

Bruk eksisterende `get_receipt_for_user` slik at annen bruker får 404, ikke 403.

**Tester (pytest):**

- Eier med mock storage som returnerer `b"fake-image-bytes"` → 200 og body matcher.
- Annen bruker: opprett to kontoer, last opp som A, GET som B → 404.
- Sett `image_path=""` på receipt → 410.
- Uten Authorization → 401.

Gjenbruk mønster fra `backend/tests/test_receipts.py` og `account()` i `test_phase23.py`. Patch `StorageService.download_receipt` der router/service instansierer den.

**Android Coil:**

I `libs.versions.toml`:

```toml
coil = "2.7.0"
# libraries:
coil-compose = { group = "io.coil-kt", name = "coil-compose", version.ref = "coil" }
```

`NetworkModule`: provide `ImageLoader` singleton:

```kotlin
@Provides @Singleton
fun provideImageLoader(@ApplicationContext context: Context, client: OkHttpClient): ImageLoader =
    ImageLoader.Builder(context).okHttpClient(client).build()
```

I `PrislappApplication` (allerede `@HiltAndroidApp`):

```kotlin
@Inject lateinit var imageLoader: ImageLoader

override fun onCreate() {
    super.onCreate()
    Coil.setImageLoader(imageLoader)
}
```

`AsyncImage` i review bruker default loader (den som ble satt over). Ikke bygg en ny OkHttpClient i UI.

**ViewModel:**

Utvid `ReceiptReviewUiState`:

```kotlin
val localImagePath: String? = null,
val imageUrl: String? = null,
```

Etter `getReceiptDetail`: `localImagePath = receiptRepository.getPendingReceiptByServerId(receiptId)?.imagePath?.takeIf { java.io.File(it).exists() }`. `imageUrl = BuildConfig.API_BASE_URL + "receipts/$receiptId/image"` (base URL har allerede trailing slash i prosjektet).

Hvis `getPendingReceiptByServerId` ikke finnes på repository: wrap `pendingReceiptDao.getByServerReceiptId` og sjekk `userId == tokenStore.getUserId()`.

UI: hvis `localImagePath != null` bruk `File`. Ellers `AsyncImage(model = imageUrl, imageLoader = ..., contentScale = ContentScale.Crop, modifier = height(180.dp).fillMaxWidth())`. `error`/`fallback`: `Text(stringResource(R.string.image_unavailable))`.

- [ ] Pytest grønn: `cd backend && .venv/bin/python -m pytest tests/test_receipt_image.py -v`
- [ ] `./gradlew :app:testDebugUnitTest --tests no.prislapp.ui.receipt.ReceiptReviewViewModelTest`
- [ ] Commit `feat(api): serve receipt image for review` og eventuelt separat `feat(ui): show receipt image on review` hvis du splitter — én commit er OK hvis begge er i samme task.

**Done when:** 200/404/410/401 dekket. Review viser bilde eller `image_unavailable`. Bekreftelses-tester fortsatt grønne.

---

### Task 6: Behandlingsskjerm med menneskelig ventetekst

**Depends on:** Task 1, Task 2 (`PrislappTopBar`).

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptScreens.kt` (`ReceiptProcessingScreen` only)

**Regler:**

- Toppbar: `PrislappTopBar(stringResource(R.string.processing_title), onBack = onBack)`
- Aldri `processing_status` / `Status: %1$s`
- Body:
  - status in `PENDING`, `UPLOADING`, `UPLOADED` → `processing_body_upload`
  - `PROCESSING` → `processing_body_ocr`
  - `FAILED` eller `error != null` → `processing_body_failed` + `OutlinedButton` retry som i dag
  - ellers `receiptStatusLabel(status)`
- Spinner når `isPolling`

Pipeline/ViewModel uendret.

- [ ] Commit `feat(ui): explain receipt processing in plain language`

**Done when:** Ingen enum synlig på behandlingsskjermen.

---

### Task 7: Historikk – rader og FlowRow-filter

**Depends on:** Task 1, Task 2. Hvis Task 4 er merget: ingen tilbake-knapp.

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/history/HistoryScreen.kt`

**Regler:**

- `PrislappTopBar(history_title, onBack = onBack)` — send `onBack = null` fra NavHost hvis tab (Task 4). Hvis `onBack` fortsatt er påkrevd i signaturen, vis ikon kun når lambda skal poppe; Task 4 skal sette den ubrukt. Konkret: endre til `onBack: (() -> Unit)? = null` og vis tilbake kun hvis ikke null.
- Butikkchips i `FlowRow(horizontalArrangement = spacedBy(8.dp), verticalArrangement = spacedBy(8.dp))`. `@OptIn(ExperimentalLayoutApi::class)` hvis kompilatoren krever det.
- Kvitteringer: `ReceiptRow(title = store ?: unknown_store, subtitle = formatReceiptSubtitle(purchase_date, total), statusLabel = null, onClick = { onOpenReceipt(id) })`.
- Tom og ikke lasting: `EmptyState(stringResource(R.string.history_empty_title), stringResource(R.string.history_empty_body))`. Ikke vis `no_receipts` på denne skjermen.
- Datofilter, load more, error/retry uendret.

- [ ] Commit `feat(ui): present history as rows with wrapping filters`

**Done when:** Ingen `OutlinedButton` som kvitteringsrad. Chips wrappes horisontalt.

---

### Task 8: Live produktsøk

**Depends on:** ingen. Oppdater instrumentering hvis Task 4 er inne.

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/product/ProductSearchViewModel.kt`
- Modify: `android/app/src/main/java/no/prislapp/ui/product/ProductScreens.kt`
- Modify: `android/app/src/test/java/no/prislapp/ui/product/ProductSearchViewModelTest.kt`
- Modify: `android/app/src/androidTest/java/no/prislapp/AuthNavigationTest.kt` — fjern klikk på «Søk»-knappen; vent på tom-resultat etter typing

**ViewModel:**

```kotlin
fun updateQuery(value: String) {
    searchJob?.cancel()
    val trimmed = value
    _uiState.update {
        it.copy(query = trimmed, error = null)
    }
    if (trimmed.trim().length < 2) {
        _uiState.update { it.copy(results = emptyList(), isSearching = false, hasSearched = false) }
        return
    }
    searchJob = viewModelScope.launch {
        delay(300)
        _uiState.update { it.copy(isSearching = true) }
        try {
            val response = productRepository.searchProducts(trimmed.trim())
            _uiState.update {
                it.copy(isSearching = false, results = response.items, hasSearched = true)
            }
        } catch (e: CancellationException) { throw e
        } catch (e: Exception) {
            _uiState.update { it.copy(isSearching = false, error = e.message ?: "Søk feilet") }
        }
    }
}
```

Fjern `fun search()` og Søk-knappen. All søking skjer fra `updateQuery`. Oppdater `ProductSearchViewModelTest.clearingQueryClearsPreviousResults` så den bare kaller `updateQuery` + `advanceTimeBy`/`advanceUntilIdle`, ikke `search()`.

**Tester:**

- `updateQuery("m")` → ingen `searchProducts`, tom results.
- `updateQuery("melk")`; `advanceTimeBy(299)` → ingen kall; `advanceTimeBy(1)` + `advanceUntilIdle()` → ett kall.
- `updateQuery("melk")` deretter `updateQuery("mel")` før delay → bare siste query kalles.
- `updateQuery("melk")` + idle, deretter `updateQuery("")` → results empty, ingen ekstra kall etter clear.

Bruk `StandardTestDispatcher` og `advanceTimeBy`.

**UI:** Fjern Søk-`Button`. Resultater som `ReceiptRow`/`ListItem` med kun title = `canonical_name`.

- [ ] `./gradlew :app:testDebugUnitTest --tests no.prislapp.ui.product.ProductSearchViewModelTest`
- [ ] Commit `feat(ui): search products as you type`

**Done when:** Debounce-tester grønne. Ingen Søk-knapp. Instrumentering venter ikke på noden «Søk» som knapp (bunnnav-label «Søk» kan fortsatt finnes — bruk `hasSetTextAction()` på feltet, ikke knappen).

---

### Task 9: Billigst-for-meg som hero

**Depends on:** ingen.

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/product/ProductScreens.kt` (`ProductPricesScreen` only)

**Regler fra spec «Billigst for meg».** Bruk `Card` for cheapest. Dato `take(10)` formatert via samme `formatReceiptSubtitle(observed_at, null)` eller `dd.MM.yyyy`. Pris med `kr`. Ingen knapper. `no_price_observations` når cheapest er null og observations tom.

Toppbar: `PrislappTopBar(cheapest_for_me_title, onBack = onBack)`.

- [ ] Commit `feat(ui): highlight cheapest store on product prices`

**Done when:** Billigste treff er visuelt først. To lister er seksjoner, ikke like tekstblokker uten hierarki.

---

### Task 10: Gjennomgang – dato, kort, skjult OCR

**Depends on:** Task 2, Task 5 (bilde beholdes øverst).

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/receipt/ReceiptScreens.kt`
- Modify: `android/app/src/test/java/no/prislapp/ui/receipt/ReceiptReviewViewModelTest.kt` — eksisterende dato-test skal fortsatt passere (`updatePurchaseDate("11.08.2026")` forblir gyldig)

**Regler:**

- Kjøpsdato-felt `readOnly = true` alltid. `Modifier.clickable` når `!isReadOnly` åpner `DatePickerDialog` kopiert fra `HistoryScreen` (samme UTC millis-hjelpere). Valgt dato skrives med `DateTimeFormatter.ofPattern("dd.MM.yyyy")` inn i `viewModel.updatePurchaseDate`.
- Varelinjer: `OutlinedCard` per item. `remove_item` = `TextButton`.
- `add_item` = `TextButton`.
- `confirm_receipt` beholdes som fylt `Button` full bredde.
- OCR: `var showOcr by remember { mutableStateOf(false) }`. `TextButton` veksler `show_ocr` / `hide_ocr`. Vis `rawOcrText` kun når `showOcr && rawOcrText.isNotBlank()`.
- Slettedialog: `dismissButton` bruker `R.string.cancel`.
- Ikke fjern bildet fra Task 5.

- [ ] `./gradlew :app:testDebugUnitTest --tests no.prislapp.ui.receipt.ReceiptReviewViewModelTest`
- [ ] Commit `feat(ui): tighten receipt review editing layout`

**Done when:** Dato velges i dialog, OCR skjult som standard, linjer i kort, slett bruker «Avbryt».

---

### Task 11: Kamera-lukker

**Depends on:** Task 2 (toppbar).

**Files:**
- Modify: `android/app/src/main/java/no/prislapp/ui/camera/CameraScreen.kt`

**Regler:**

- `PrislappTopBar(camera_title, onBack = onBack)`
- Erstatt tekst-`Button` «Ta bilde» med `FilledIconButton` eller `Box` 72.dp `clip(CircleShape)` `background(MaterialTheme.colorScheme.primary)` + `Icon(Icons.Default.CameraAlt, contentDescription = capture_button)` hvit. Disable når `capturing || provider == null`.
- Galleri: `IconButton` + `Icons.Default.PhotoLibrary` + `pick_from_gallery` contentDescription. Fjern `OutlinedButton`-tekst.
- Pipeline (`onPhotoCaptured`, tillatelse, PreviewView COMPATIBLE) uendret.
- Veiledningstekst beholdes.

- [ ] Commit `feat(ui): use shutter control on camera`

**Done when:** Ingen tekstknapp for capture/galleri. Capture-kjeden uendret.

---

### Task 12: Verifikasjon og instrumentering

**Depends on:** Task 4, 8, 10 (og helst alle).

**Files:**
- Modify: `android/app/src/androidTest/java/no/prislapp/AuthNavigationTest.kt` hvis rester gjenstår
- Grep: ingen synlige `PROCESSING`/`PENDING`/`Tilbake` som `TextButton`-label i `ui/`

**Grep-sjekk (må være tom for UI-bruk, tester/DTO kan ha enums):**

```bash
rg "OutlinedButton" android/app/src/main/java/no/prislapp/ui/home android/app/src/main/java/no/prislapp/ui/history android/app/src/main/java/no/prislapp/ui/product
rg "processing_status|Status:" android/app/src/main/java
rg "stringResource\\(R.string.back\\)" android/app/src/main/java  # OK inne i Icon contentDescription, ikke Text(
```

`AuthNavigationTest` endelig flyt:

1. Login som i dag.
2. Vent på FAB/`capture_receipt` eller tittel Prislapp — ikke på synlig «Logg ut».
3. `Historikk` (nav) → `Søk` (nav) uten tilbake.
4. Skriv «melk» i søkefelt. Ikke klikk knapp «Søk». Vent på `no_products`.
5. Overflow Konto → Logg ut → login vises.

Kjør:

```bash
cd backend && .venv/bin/python -m pytest tests/test_receipt_image.py tests/test_receipts.py -q
cd ../android && ./gradlew assembleDebug testDebugUnitTest lintDebug
```

Instrumentering kun hvis emulator + `10.0.2.2:18000` er oppe:

```bash
./gradlew connectedDebugAndroidTest -PapiBaseUrl=http://10.0.2.2:18000/
```

- [ ] Fiks det grep eller tester avslører.
- [ ] Commit kun hvis du måtte fikse: `fix(ui): align navigation test with new chrome`

**Done when:** Unit + lint grønne. Spec-akseptansekriteriene kan hukes av manuelt på enhet.

---

## Self-review

| Spec-krav | Task |
|-----------|------|
| Statuskopi, ingen enums | 1, 3, 6, 7 |
| ReceiptRow / tomtilstand / tilbake-ikon | 2, 3, 7 |
| FAB + logout overflow | 3 |
| Bunnnav | 4 |
| Bilde i gjennomgang + GET image | 5 |
| Processing-tekst | 6 |
| Historikk rader + FlowRow | 7 |
| Live-søk | 8 |
| Pris-hero | 9 |
| Dato, kort, OCR collapse | 10 |
| Kamera-lukker | 11 |
| Instrumentering | 3, 4, 8, 12 |

Ingen TBD. Ingen «lignende task N» uten gjentatt kontrakt.
