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
import no.prislapp.data.repository.AddItemResult
import no.prislapp.data.repository.ShoppingListRepository
import org.junit.*
import org.junit.Assert.*
import java.math.BigDecimal

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
    fun emptyRepoCreatesDefaultListOnceAndRefreshDoesNotCreateAnother() = runTest(dispatcher) {
        val fixture = Fixture()
        coEvery { fixture.repo.createList(any()) } returns "list-1"
        val vm = ShoppingListViewModel(fixture.repo)
        advanceUntilIdle()
        coVerify(exactly = 1) { fixture.repo.createList("Handleliste") }

        vm.refresh()
        advanceUntilIdle()
        coVerify(exactly = 1) { fixture.repo.createList(any()) }
        assertEquals("list-1", vm.uiState.value.listId)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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
        val vm = ShoppingListViewModel(fixture.repo)
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

    private class Fixture {
        val lists = MutableStateFlow<List<ShoppingListEntity>>(emptyList())
        val items = MutableStateFlow<List<ShoppingListItemEntity>>(emptyList())
        val conflicts = MutableStateFlow<List<SyncConflictEntity>>(emptyList())
        val products = MutableStateFlow<List<CachedUserProductEntity>>(emptyList())
        val repo = mockk<ShoppingListRepository>()

        init {
            every { repo.observeLists() } returns lists
            every { repo.observeItems(any()) } returns items
            every { repo.observeConflicts() } returns conflicts
            every { repo.observeRecentProducts() } returns products
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
}
