package no.prislapp.ui.product

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import no.prislapp.data.remote.dto.ProductSummaryResponse
import no.prislapp.data.repository.ProductRepository
import javax.inject.Inject

data class ProductSearchUiState(
    val query: String = "",
    val results: List<ProductSummaryResponse> = emptyList(),
    val isSearching: Boolean = false,
    val error: String? = null,
    val hasSearched: Boolean = false,
)

@HiltViewModel
class ProductSearchViewModel @Inject constructor(
    private val productRepository: ProductRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ProductSearchUiState())
    val uiState: StateFlow<ProductSearchUiState> = _uiState.asStateFlow()
    private var searchJob: Job? = null

    fun updateQuery(value: String) {
        searchJob?.cancel()
        _uiState.update { it.copy(query = value, results = emptyList(), isSearching = false, hasSearched = false) }
    }

    fun search() {
        val query = _uiState.value.query.trim()
        if (query.isEmpty()) return

        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            _uiState.update { it.copy(isSearching = true, error = null) }
            try {
                val response = productRepository.searchProducts(query)
                _uiState.update {
                    it.copy(isSearching = false, results = response.items, hasSearched = true)
                }
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isSearching = false,
                        error = e.message ?: "Søk feilet",
                    )
                }
            }
        }
    }
}
