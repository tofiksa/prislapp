package no.prislapp.ui.product

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import no.prislapp.data.remote.dto.ProductSummaryResponse
import no.prislapp.data.repository.ProductRepository
import javax.inject.Inject

data class ProductSearchUiState(
    val query: String = "",
    val results: List<ProductSummaryResponse> = emptyList(),
    val isSearching: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class ProductSearchViewModel @Inject constructor(
    private val productRepository: ProductRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ProductSearchUiState())
    val uiState: StateFlow<ProductSearchUiState> = _uiState.asStateFlow()

    fun updateQuery(value: String) {
        _uiState.update { it.copy(query = value) }
    }

    fun search() {
        val query = _uiState.value.query.trim()
        if (query.isEmpty()) return

        viewModelScope.launch {
            _uiState.update { it.copy(isSearching = true, error = null) }
            try {
                val response = productRepository.searchProducts(query)
                _uiState.update {
                    it.copy(isSearching = false, results = response.items)
                }
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
