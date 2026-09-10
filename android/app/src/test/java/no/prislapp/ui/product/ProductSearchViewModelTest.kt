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
    @Test fun clearingQueryClearsPreviousResults() = runTest {
        val repo = mockk<ProductRepository>()
        coEvery { repo.searchProducts("melk") } returns ProductSearchResponse(listOf(ProductSummaryResponse("p", "Melk", null)))
        val vm = ProductSearchViewModel(repo)
        vm.updateQuery("melk"); vm.search(); advanceUntilIdle()
        assertEquals(1, vm.uiState.value.results.size)
        vm.updateQuery(""); vm.search(); advanceUntilIdle()
        assertTrue(vm.uiState.value.results.isEmpty())
    }
}
