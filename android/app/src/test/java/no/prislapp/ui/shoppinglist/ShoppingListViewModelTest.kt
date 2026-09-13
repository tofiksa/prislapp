package no.prislapp.ui.shoppinglist

import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.*
import no.prislapp.data.local.entity.CachedUserProductEntity
import no.prislapp.data.local.entity.ShoppingListEntity
import no.prislapp.data.local.entity.ShoppingListItemEntity
import no.prislapp.data.local.entity.SyncConflictEntity
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryDto
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryLineDto
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryLowestDto
import no.prislapp.data.repository.AddItemResult
import no.prislapp.data.repository.CachedPriceSummary
import no.prislapp.data.repository.PriceSummaryRepository
import no.prislapp.data.repository.ReceiptRepository
import no.prislapp.data.repository.ShoppingListRepository
import org.junit.*
import org.junit.Assert.*
import java.io.IOException
import java.math.BigDecimal
import kotlinx.coroutines.delay

@OptIn(ExperimentalCoroutinesApi::class)
class ShoppingListViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun cleanup() {
        Dispatchers.resetMain()
        unmockkAll()
    }

    @Test
    fun initResumesPendingReceiptAndShoppingListWork() {
        val fixture = Fixture()
        fixture.createViewModel()

        verify { fixture.receiptRepo.resumePendingWork() }
        verify { fixture.repo.resumePendingWork() }
    }

    @Test
    fun firstReceiptCtaCatalogAddsThreeProductsByIdNeverFreeText() = runTest(dispatcher) {
        val fixture = Fixture()
        val products = (1..3).map { index ->
            CachedUserProductEntity(
                id = "p$index",
                userId = "user-a",
                displayName = "Vare $index",
                packUnit = "each",
            )
        }
        fixture.products.value = products
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.applyFirstReceiptCta(confirmedLineCount = 3)
        assertEquals(3, vm.uiState.value.firstReceiptCtaCount)

        vm.acceptFirstReceiptCta()
        assertTrue(vm.uiState.value.showAddSheet)
        assertNull(vm.uiState.value.firstReceiptCtaCount)

        products.forEach { vm.addRecentProduct(it.id) }
        advanceUntilIdle()

        products.forEach { product ->
            coVerify {
                fixture.repo.addProductOrIncrement(
                    listId = "list-1",
                    userProductId = product.id,
                    productDisplayName = product.displayName,
                    quantity = BigDecimal.ONE,
                    quantityUnit = "each",
                )
            }
        }
        coVerify(exactly = 0) { fixture.repo.addItem(any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun firstReceiptCtaHiddenWhenListAlreadyHasThreeHistoricalItems() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.items.value = listOf(
            item(id = "h1", userProductId = "p1"),
            item(id = "h2", userProductId = "p2"),
            item(id = "h3", userProductId = "p3"),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.applyFirstReceiptCta(confirmedLineCount = 5)
        assertNull(vm.uiState.value.firstReceiptCtaCount)
        assertFalse(vm.uiState.value.showAddSheet)
    }

    @Test
    fun emptyRepoCreatesDefaultListOnceAndRefreshDoesNotCreateAnother() = runTest(dispatcher) {
        val fixture = Fixture()
        coEvery { fixture.repo.createList(any()) } returns "list-1"
        val vm = fixture.createViewModel()
        advanceUntilIdle()
        coVerify(exactly = 1) { fixture.repo.createList("Handleliste") }

        vm.refresh()
        advanceUntilIdle()
        coVerify(exactly = 1) { fixture.repo.createList(any()) }
        assertEquals("list-1", vm.uiState.value.listId)
    }

    @Test
    fun finishTripKeepingUncheckedShowsTheCopyNotTheArchivedSource() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(
            item(id = "keep", freeText = "Brød", checked = false),
            item(id = "drop", freeText = "Melk", checked = true),
        )
        coEvery { fixture.repo.finishTrip("list-1", true) } coAnswers {
            fixture.lists.value = listOf(
                listEntity().copy(status = ShoppingListEntity.STATUS_ARCHIVED),
                ShoppingListEntity(
                    id = "list-2",
                    userId = "user-a",
                    name = "Handleliste",
                    createdAt = "2026-09-11T12:00:00Z",
                    updatedAt = "2026-09-11T12:00:00Z",
                ),
            )
            fixture.items.value = listOf(
                item(id = "new-keep", freeText = "Brød").copy(listId = "list-2"),
            )
            "list-2"
        }
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.finishTrip(keepUnchecked = true)
        advanceUntilIdle()

        assertEquals("list-2", vm.uiState.value.listId)
        assertEquals(listOf("new-keep"), vm.uiState.value.items.map { it.id })
        assertTrue(vm.uiState.value.items.none { it.checked })
        assertTrue(vm.uiState.value.showAddReceiptPrompt)
    }

    @Test
    fun finishTripWithoutKeepingLeavesANewActiveListNotTheArchivedOne() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", freeText = "Melk"))
        coEvery { fixture.repo.finishTrip("list-1", false) } coAnswers {
            fixture.lists.value = listOf(
                listEntity().copy(status = ShoppingListEntity.STATUS_ARCHIVED),
                ShoppingListEntity(
                    id = "list-2",
                    userId = "user-a",
                    name = "Handleliste",
                    createdAt = "2026-09-11T12:00:00Z",
                    updatedAt = "2026-09-11T12:00:00Z",
                ),
            )
            fixture.items.value = emptyList()
            "list-2"
        }
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.finishTrip(keepUnchecked = false)
        advanceUntilIdle()

        assertEquals("list-2", vm.uiState.value.listId)
        assertTrue(vm.uiState.value.items.isEmpty())
        assertTrue(vm.uiState.value.showAddReceiptPrompt)
    }

    @Test
    fun doubleFinishTripInMutexDoesNotArchiveTwice() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        coEvery { fixture.repo.finishTrip(any(), any()) } coAnswers {
            delay(50)
            "list-2"
        }
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.finishTrip(keepUnchecked = true)
        vm.finishTrip(keepUnchecked = true)
        advanceUntilIdle()

        coVerify(exactly = 1) { fixture.repo.finishTrip("list-1", true) }
    }

    @Test
    fun checkingAnItemDoesNotArchiveTheList() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", freeText = "Melk"))
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.setChecked("item-1", true)
        advanceUntilIdle()

        coVerify { fixture.repo.setItemChecked("list-1", "item-1", true) }
        coVerify(exactly = 0) { fixture.repo.setListArchived(any(), any()) }
        coVerify(exactly = 0) { fixture.repo.finishTrip(any(), any()) }
        assertEquals("list-1", vm.uiState.value.listId)
    }

    @Test
    fun afterTheActiveListDisappearsANewDefaultListIsCreated() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        val vm = fixture.createViewModel()
        advanceUntilIdle()
        clearMocks(fixture.repo, answers = false, recordedCalls = true)
        coEvery { fixture.repo.createList(any()) } coAnswers {
            fixture.lists.value = listOf(
                ShoppingListEntity(
                    id = "list-2",
                    userId = "user-a",
                    name = "Handleliste",
                    createdAt = "2026-09-11T12:00:00Z",
                    updatedAt = "2026-09-11T12:00:00Z",
                ),
            )
            "list-2"
        }

        fixture.lists.value = listOf(listEntity().copy(status = ShoppingListEntity.STATUS_ARCHIVED))
        advanceUntilIdle()

        coVerify(exactly = 1) { fixture.repo.createList("Handleliste") }
        assertEquals("list-2", vm.uiState.value.listId)
    }

    @Test
    fun tenCachedProductsAreAddedByUserProductIdNeverFreeText() = runTest(dispatcher) {
        val fixture = Fixture()
        val products = (1..10).map { index ->
            CachedUserProductEntity(
                id = "p$index",
                userId = "user-a",
                displayName = "Vare $index",
                packUnit = "each",
            )
        }
        fixture.products.value = products
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        products.forEach { vm.addRecentProduct(it.id) }
        advanceUntilIdle()

        products.forEach { product ->
            coVerify {
                fixture.repo.addProductOrIncrement(
                    listId = "list-1",
                    userProductId = product.id,
                    productDisplayName = product.displayName,
                    quantity = BigDecimal.ONE,
                    quantityUnit = "each",
                )
            }
        }
        coVerify(exactly = 0) { fixture.repo.addItem(any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun freeTextLineHasNoPriceHistoryAndNullUserProductId() = runTest(dispatcher) {
        val fixture = Fixture()
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        fixture.items.value = listOf(
            item(id = "ft-1", freeText = "Rømme", userProductId = null),
        )
        advanceUntilIdle()

        val row = vm.uiState.value.items.single()
        assertEquals("Rømme", row.displayName)
        assertTrue(row.noPriceHistory)
        assertNull(row.userProductId)
        assertEquals("Ingen prishistorikk", row.priceHistoryLabel)
    }

    @Test
    fun setItemCheckedDoesNotRequireNetworkOrSync() = runTest(dispatcher) {
        val fixture = Fixture()
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        clearMocks(fixture.repo, answers = false, recordedCalls = true)
        vm.setChecked("item-1", true)
        advanceUntilIdle()

        coVerify { fixture.repo.setItemChecked("list-1", "item-1", true) }
        coVerify(exactly = 0) { fixture.repo.syncPending() }
        coVerify(exactly = 0) { fixture.repo.refreshRecentProducts() }
    }

    @Test
    fun secondAddOfSameProductIncrementsQuantityAndUndoRestoresPrevious() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.products.value = listOf(
            CachedUserProductEntity(
                id = "p-melk",
                userId = "user-a",
                displayName = "Melk",
                packUnit = "each",
            ),
        )
        coEvery {
            fixture.repo.addProductOrIncrement(any(), eq("p-melk"), any(), any(), any())
        } returnsMany listOf(
            AddItemResult(itemId = "item-1", previousQuantity = null),
            AddItemResult(itemId = "item-1", previousQuantity = BigDecimal("1.000")),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.addRecentProduct("p-melk")
        advanceUntilIdle()
        vm.addRecentProduct("p-melk")
        advanceUntilIdle()

        coVerify(exactly = 2) {
            fixture.repo.addProductOrIncrement(any(), eq("p-melk"), any(), any(), any())
        }
        val undo = vm.uiState.value.pendingUndo
        assertTrue(undo is ShoppingListUndo.RestoreQuantity)
        assertEquals("item-1", (undo as ShoppingListUndo.RestoreQuantity).itemId)

        vm.undo()
        advanceUntilIdle()
        coVerify {
            fixture.repo.setItemQuantity(
                "list-1",
                "item-1",
                match { it.compareTo(BigDecimal.ONE) == 0 },
            )
        }
    }

    @Test
    fun mergeUndoKeepsAddSheetOpenAndHostsSnackbarOnSheet() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.products.value = listOf(
            CachedUserProductEntity(
                id = "p-melk",
                userId = "user-a",
                displayName = "Melk",
                packUnit = "each",
            ),
        )
        var addCount = 0
        coEvery {
            fixture.repo.addProductOrIncrement(any(), eq("p-melk"), any(), any(), any())
        } coAnswers {
            fixture.items.value = listOf(
                item(id = "item-1", userProductId = "p-melk"),
            )
            val previous = if (addCount == 0) null else BigDecimal("$addCount.000")
            addCount++
            AddItemResult(itemId = "item-1", previousQuantity = previous)
        }
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.openAddSheet()
        assertTrue(vm.uiState.value.showAddSheet)

        vm.addRecentProduct("p-melk")
        advanceUntilIdle()
        assertTrue(vm.uiState.value.showAddSheet)
        assertFalse(vm.uiState.value.undoSnackbarOnSheet)

        vm.addRecentProduct("p-melk")
        advanceUntilIdle()
        assertTrue(vm.uiState.value.showAddSheet)
        assertTrue(vm.uiState.value.pendingUndo is ShoppingListUndo.RestoreQuantity)
        assertTrue(vm.uiState.value.undoSnackbarOnSheet)

        vm.addRecentProduct("p-melk")
        advanceUntilIdle()
        assertTrue(vm.uiState.value.showAddSheet)
        assertTrue(vm.uiState.value.undoSnackbarOnSheet)

        vm.dismissAddSheet()
        assertFalse(vm.uiState.value.showAddSheet)
        assertFalse(vm.uiState.value.undoSnackbarOnSheet)
        assertTrue(vm.uiState.value.pendingUndo is ShoppingListUndo.RestoreQuantity)
    }

    @Test
    fun deleteUndoDoesNotHostSnackbarOnSheet() = runTest(dispatcher) {
        val fixture = Fixture()
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.deleteItem("item-1")
        advanceUntilIdle()

        assertFalse(vm.uiState.value.showAddSheet)
        assertFalse(vm.uiState.value.undoSnackbarOnSheet)
        assertTrue(vm.uiState.value.pendingUndo is ShoppingListUndo.Undelete)
    }

    @Test
    fun freeTextMelkIsNotMergedWithProductMelk() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.products.value = listOf(
            CachedUserProductEntity(
                id = "p-melk",
                userId = "user-a",
                displayName = "Melk",
                packUnit = "each",
            ),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        vm.addRecentProduct("p-melk")
        vm.addFreeText("Melk")
        advanceUntilIdle()

        coVerify {
            fixture.repo.addProductOrIncrement(
                listId = "list-1",
                userProductId = "p-melk",
                productDisplayName = "Melk",
                quantity = BigDecimal.ONE,
                quantityUnit = "each",
            )
        }
        coVerify {
            fixture.repo.addItem(
                listId = "list-1",
                freeText = "Melk",
                userProductId = null,
                productDisplayName = null,
                quantity = BigDecimal.ONE,
                quantityUnit = "each",
            )
        }
    }

    @Test
    fun checkedItemsAreSortedLastInUiState() = runTest(dispatcher) {
        val fixture = Fixture()
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        fixture.items.value = listOf(
            item(id = "checked", freeText = "Smør", checked = true, position = 0),
            item(id = "open", freeText = "Melk", checked = false, position = 1),
        )
        advanceUntilIdle()

        assertEquals(listOf("open", "checked"), vm.uiState.value.items.map { it.id })
    }

    @Test
    fun conflictBannerShowsWhenConflictsArePresent() = runTest(dispatcher) {
        val fixture = Fixture()
        val vm = fixture.createViewModel()
        advanceUntilIdle()
        assertFalse(vm.uiState.value.showConflictBanner)

        fixture.conflicts.value = listOf(
            SyncConflictEntity(
                mutationId = "m1",
                userId = "user-a",
                operation = "item_patch",
                code = "VERSION_CONFLICT",
                message = "Konflikt",
                localJson = "{}",
            ),
        )
        advanceUntilIdle()
        assertTrue(vm.uiState.value.showConflictBanner)
    }

    @Test
    fun setCheckedStillCallsSetItemCheckedWhenPriceFetchThrows() = runTest(dispatcher) {
        val fixture = Fixture()
        coEvery { fixture.priceRepo.refresh(any()) } throws IOException("nett nede")
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        advanceUntilIdle()
        clearMocks(fixture.repo, answers = false, recordedCalls = true)

        vm.setChecked("item-1", true)
        advanceUntilIdle()

        coVerify { fixture.repo.setItemChecked("list-1", "item-1", true) }
        coVerify(exactly = 0) { fixture.repo.setItemChecked("list-1", "item-1", false) }
    }

    @Test
    fun staleSummaryWithLowerContentRevisionDoesNotReplaceLinePrices() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity(contentRevision = 10))
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        coEvery { fixture.priceRepo.refresh(any()) } returnsMany listOf(
            priceSummary(contentRevision = 10, lines = listOf(lowestLine("item-1", "24.90", storeCount = 2))),
            priceSummary(contentRevision = 9, lines = listOf(lowestLine("item-1", "1.00", storeCount = 2))),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        val first = vm.uiState.value.items.single().priceLabel
        assertNotNull(first)
        assertTrue(first!!.contains("24,90"))
        assertTrue(first.contains("Lavest registrert"))

        vm.refreshPrices()
        advanceUntilIdle()

        val second = vm.uiState.value.items.single().priceLabel
        assertEquals(first, second)
        assertTrue(!second!!.contains("1,00"))
        assertTrue(!second.contains("1.00"))
    }

    @Test
    fun nullHistoricalLowestFormatsAsNoComparablePriceNeverZero() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        coEvery { fixture.priceRepo.refresh(any()) } returns priceSummary(
            lines = listOf(
                ShoppingListPriceSummaryLineDto(
                    item_id = "item-1",
                    product_id = "p1",
                    quantity = "1.000",
                    quantity_unit = "each",
                    status = "no_comparable_price",
                    reason = "never_observed",
                    eligible_store_count = 0,
                    historical_lowest = null,
                ),
            ),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        val label = vm.uiState.value.items.single().priceLabel
        assertNotNull(label)
        assertTrue(label!!.contains("Ingen sammenlignbar pris"))
        assertTrue(label.contains("Aldri registrert"))
        assertTrue(!label.contains("0,00"))
        assertTrue(!label.contains("0.00"))
        assertTrue(!label.contains("Lavest registrert"))
    }

    @Test
    fun cachedSummaryShownWithFetchedAtAndFailedRefreshKeepsCacheAndErrorFlag() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        val cached = priceSummary(
            lines = listOf(lowestLine("item-1", "24.90", storeCount = 2)),
        )
        coEvery { fixture.priceRepo.cached(any()) } returns CachedPriceSummary(
            summary = cached,
            fetchedAt = "2026-09-10T12:00:00Z",
        )
        coEvery { fixture.priceRepo.refresh(any()) } throws IOException("timeout")
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        val state = vm.uiState.value
        assertEquals("Priser hentet 10.09.2026", state.pricesFetchedAtLabel)
        assertTrue(state.priceRefreshFailed)
        val label = state.items.single().priceLabel
        assertNotNull(label)
        assertTrue(label!!.contains("24,90"))
        assertTrue(!label.contains("0,00"))
    }

    @Test
    fun oneEligibleStoreUsesComparisonDisabledCopy() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        coEvery { fixture.priceRepo.refresh(any()) } returns priceSummary(
            lines = listOf(lowestLine("item-1", "24.90", storeCount = 1, storeName = "Kiwi Grünerløkka")),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        val label = vm.uiState.value.items.single().priceLabel
        assertNotNull(label)
        assertTrue(label!!.contains("Registrert hos Kiwi Grünerløkka — ingen butikksammenligning ennå"))
        assertTrue(!label.contains("Lavest registrert"))
        assertTrue(label.contains("24,90"))
    }

    @Test
    fun freeTextReasonMapsToNoPriceHistoryNeverZero() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "ft-1", freeText = "Melk", userProductId = null))
        coEvery { fixture.priceRepo.refresh(any()) } returns priceSummary(
            lines = listOf(
                ShoppingListPriceSummaryLineDto(
                    item_id = "ft-1",
                    free_text = "Melk",
                    quantity = "1.000",
                    quantity_unit = "each",
                    status = "no_comparable_price",
                    reason = "free_text_no_history",
                    eligible_store_count = 0,
                    historical_lowest = null,
                ),
            ),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()

        val row = vm.uiState.value.items.single()
        assertTrue(row.noPriceHistory)
        assertEquals("Ingen prishistorikk", row.priceHistoryLabel)
        assertEquals("Ingen prishistorikk", row.priceLabel)
        assertTrue(!row.priceLabel!!.contains("0,00"))
        assertTrue(!row.priceLabel!!.contains("0.00"))
    }

    @Test
    fun loadingWithoutCacheTimesOutToRetryCopy() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity())
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        coEvery { fixture.priceRepo.refresh(any()) } coAnswers {
            delay(20_000)
            priceSummary(lines = listOf(lowestLine("item-1", "24.90", storeCount = 2)))
        }
        val vm = fixture.createViewModel()
        advanceTimeBy(1)
        val loading = vm.uiState.value.items.single().priceLabel
        assertEquals("Henter pris…", loading)
        assertTrue(!vm.uiState.value.items.single().showPriceRetry)

        advanceTimeBy(ShoppingListViewModel.PRICE_FETCH_TIMEOUT_MS)
        advanceUntilIdle()

        val failed = vm.uiState.value.items.single()
        assertEquals("Kunne ikke hente pris", failed.priceLabel)
        assertTrue(failed.showPriceRetry)
        assertTrue(!failed.priceLabel!!.contains("0,00"))
    }

    @Test
    fun localItemChangeHidesStaleLinePriceUntilContentRevisionMatches() = runTest(dispatcher) {
        val fixture = Fixture()
        fixture.lists.value = listOf(listEntity(contentRevision = 3))
        fixture.items.value = listOf(item(id = "item-1", userProductId = "p1"))
        coEvery { fixture.priceRepo.refresh(any()) } returns priceSummary(
            contentRevision = 3,
            lines = listOf(lowestLine("item-1", "24.90", storeCount = 2)),
        )
        val vm = fixture.createViewModel()
        advanceUntilIdle()
        assertTrue(vm.uiState.value.items.single().priceLabel!!.contains("24,90"))

        fixture.items.value = listOf(
            item(id = "item-1", userProductId = "p1"),
            item(id = "item-2", freeText = "Brød"),
        )
        advanceUntilIdle()

        val labels = vm.uiState.value.items.associate { it.id to it.priceLabel }
        assertEquals("Pris oppdateres etter synkronisering", labels["item-1"])
        assertEquals("Pris oppdateres etter synkronisering", labels["item-2"])
        assertTrue(labels.values.none { it!!.contains("24,90") })
    }

    private class Fixture {
        val lists = MutableStateFlow<List<ShoppingListEntity>>(emptyList())
        val items = MutableStateFlow<List<ShoppingListItemEntity>>(emptyList())
        val conflicts = MutableStateFlow<List<SyncConflictEntity>>(emptyList())
        val products = MutableStateFlow<List<CachedUserProductEntity>>(emptyList())
        val repo = mockk<ShoppingListRepository>()
        val priceRepo = mockk<PriceSummaryRepository>()
        val receiptRepo = mockk<ReceiptRepository>(relaxUnitFun = true)

        fun createViewModel() = ShoppingListViewModel(repo, priceRepo, receiptRepo)

        init {
            every { repo.observeLists() } returns lists
            every { repo.observeItems(any()) } returns items
            every { repo.observeConflicts() } returns conflicts
            every { repo.observeRecentProducts() } returns products
            every { repo.resumePendingWork() } just Runs
            coEvery { repo.refreshRecentProducts() } just Runs
            coEvery { repo.createList(any()) } coAnswers {
                lists.value = listOf(
                    ShoppingListEntity(
                        id = "list-1",
                        userId = "user-a",
                        name = "Handleliste",
                        createdAt = "2026-01-01T00:00:00Z",
                        updatedAt = "2026-01-01T00:00:00Z",
                    ),
                )
                "list-1"
            }
            coEvery { repo.addProductOrIncrement(any(), any(), any(), any(), any()) } returns
                AddItemResult(itemId = "new-item")
            coEvery { repo.addItem(any(), any(), any(), any(), any(), any()) } returns "new-item"
            coEvery { repo.setItemChecked(any(), any(), any()) } just Runs
            coEvery { repo.setItemQuantity(any(), any(), any()) } just Runs
            coEvery { repo.setItemDeleted(any(), any(), any()) } just Runs
            coEvery { repo.syncPending() } just Runs
            coEvery { priceRepo.cached(any()) } returns null
            coEvery { priceRepo.refresh(any()) } returns priceSummary(lines = emptyList())
        }
    }

    private fun item(
        id: String,
        freeText: String? = null,
        userProductId: String? = null,
        checked: Boolean = false,
        position: Int = 0,
    ) = ShoppingListItemEntity(
        id = id,
        listId = "list-1",
        userId = "user-a",
        userProductId = userProductId,
        freeText = freeText,
        quantity = "1.000",
        quantityUnit = "each",
        checked = checked,
        position = position,
    )

    private fun listEntity(contentRevision: Int = 0) = ShoppingListEntity(
        id = "list-1",
        userId = "user-a",
        name = "Handleliste",
        contentRevision = contentRevision,
        createdAt = "2026-01-01T00:00:00Z",
        updatedAt = "2026-01-01T00:00:00Z",
    )
}

private fun priceSummary(
    contentRevision: Int = 0,
    listVersion: Int = 1,
    priceDataVersion: Int = 1,
    calculatedAt: String = "2026-09-11T07:00:00Z",
    lines: List<ShoppingListPriceSummaryLineDto>,
) = ShoppingListPriceSummaryDto(
    list_id = "list-1",
    list_version = listVersion,
    content_revision = contentRevision,
    price_data_version = priceDataVersion,
    calculated_at = calculatedAt,
    policy_version = "p0-2026-09-11",
    include_conditional = false,
    lines = lines,
)

private fun lowestLine(
    itemId: String,
    amount: String,
    storeCount: Int,
    storeName: String = "Rema 1000 Majorstuen",
) = ShoppingListPriceSummaryLineDto(
    item_id = itemId,
    product_id = "p1",
    quantity = "1.000",
    quantity_unit = "each",
    status = "historical_lowest",
    reason = null,
    eligible_store_count = storeCount,
    historical_lowest = ShoppingListPriceSummaryLowestDto(
        amount = amount,
        store_id = "store-1",
        store_name = storeName,
        identity_level = "branch",
        purchase_date = "2026-09-08",
        age_label = "registrert nylig",
        price_basis = "per_package",
        disclaimer = "Dagens pris kan være annerledes",
    ),
)
