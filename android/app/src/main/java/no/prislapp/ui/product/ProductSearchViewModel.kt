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
import kotlinx.coroutines.delay
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
}
