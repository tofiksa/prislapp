package no.prislapp.ui.product

import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import no.prislapp.data.remote.dto.ProductSearchResponse
import no.prislapp.data.remote.dto.ProductSummaryResponse
import no.prislapp.data.repository.ProductRepository
import org.junit.*
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class ProductSearchViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }

    @Test fun shortQueryDoesNotSearch() = runTest(dispatcher) {
        val repo = mockk<ProductRepository>()
        val vm = ProductSearchViewModel(repo)
        vm.updateQuery("m")
        advanceUntilIdle()
        coVerify(exactly = 0) { repo.searchProducts(any()) }
        assertTrue(vm.uiState.value.results.isEmpty())
    }

    @Test fun debounceWaits300msBeforeSearching() = runTest(dispatcher) {
        val repo = mockk<ProductRepository>()
        coEvery { repo.searchProducts("melk") } returns ProductSearchResponse(listOf(ProductSummaryResponse("p", "Melk", null)))
        val vm = ProductSearchViewModel(repo)
        vm.updateQuery("melk")
        advanceTimeBy(299)
        coVerify(exactly = 0) { repo.searchProducts(any()) }
        advanceTimeBy(1)
        advanceUntilIdle()
        coVerify(exactly = 1) { repo.searchProducts("melk") }
    }

    @Test fun rapidUpdatesSearchOnlyLastQuery() = runTest(dispatcher) {
        val repo = mockk<ProductRepository>()
        coEvery { repo.searchProducts("mel") } returns ProductSearchResponse(emptyList())
        val vm = ProductSearchViewModel(repo)
        vm.updateQuery("melk")
        vm.updateQuery("mel")
        advanceUntilIdle()
        coVerify(exactly = 1) { repo.searchProducts("mel") }
        coVerify(exactly = 0) { repo.searchProducts("melk") }
    }

    @Test fun clearingQueryClearsPreviousResults() = runTest(dispatcher) {
        val repo = mockk<ProductRepository>()
        coEvery { repo.searchProducts("melk") } returns ProductSearchResponse(listOf(ProductSummaryResponse("p", "Melk", null)))
        val vm = ProductSearchViewModel(repo)
        vm.updateQuery("melk")
        advanceUntilIdle()
        assertEquals(1, vm.uiState.value.results.size)
        vm.updateQuery("")
        advanceUntilIdle()
        assertTrue(vm.uiState.value.results.isEmpty())
        coVerify(exactly = 1) { repo.searchProducts(any()) }
    }
}
