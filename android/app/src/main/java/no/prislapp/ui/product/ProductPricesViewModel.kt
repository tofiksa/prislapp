package no.prislapp.ui.product

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import no.prislapp.data.remote.dto.ProductPricesResponse
import no.prislapp.data.repository.ProductRepository
import javax.inject.Inject

data class ProductPricesUiState(
    val isLoading: Boolean = true,
    val prices: ProductPricesResponse? = null,
    val error: String? = null,
)

@HiltViewModel
class ProductPricesViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val productRepository: ProductRepository,
) : ViewModel() {
    private val productId: String = checkNotNull(savedStateHandle["productId"])

    private val _uiState = MutableStateFlow(ProductPricesUiState())
    val uiState: StateFlow<ProductPricesUiState> = _uiState.asStateFlow()

    init {
        loadPrices()
    }

    private fun loadPrices() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val prices = productRepository.getProductPrices(productId)
                _uiState.update { it.copy(isLoading = false, prices = prices) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = e.message ?: "Kunne ikke hente priser",
                    )
                }
            }
        }
    }
}
