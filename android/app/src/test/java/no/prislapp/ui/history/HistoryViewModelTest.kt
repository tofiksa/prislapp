package no.prislapp.ui.history

import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import no.prislapp.data.remote.dto.*
import no.prislapp.data.repository.ReceiptRepository
import org.junit.*
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class HistoryViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }
    @Test fun loadsMoreThanFirstPageAndResetsWhenFilterChanges() = runTest {
        val repo = mockk<ReceiptRepository>()
        val lists = mockk<no.prislapp.data.repository.ShoppingListRepository>(relaxUnitFun = true)
        coEvery { repo.listStores() } returns StoreListResponse(emptyList())
        coEvery { repo.listReceiptsFiltered(any(), any(), any(), any(), any()) } answers {
            val page = firstArg<Int>()
            ReceiptListResponse(listOf(ReceiptSummaryResponse("$page", "CONFIRMED", null, null, null, "")), 2, page, 1)
        }
        val vm = HistoryViewModel(repo, lists)
        advanceUntilIdle()
        assertTrue(vm.uiState.value.hasMore)
        vm.loadMore(); advanceUntilIdle()
        assertEquals(listOf("1", "2"), vm.uiState.value.receipts.map { it.id })
        assertFalse(vm.uiState.value.hasMore)
        vm.selectStore("store"); advanceUntilIdle()
        assertEquals(listOf("1"), vm.uiState.value.receipts.map { it.id })
    }
}
