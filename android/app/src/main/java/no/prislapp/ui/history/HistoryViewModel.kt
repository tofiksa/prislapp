package no.prislapp.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import no.prislapp.data.remote.dto.ReceiptSummaryResponse
import no.prislapp.data.remote.dto.StoreResponse
import no.prislapp.data.repository.ReceiptRepository
import javax.inject.Inject

data class HistoryUiState(
    val receipts: List<ReceiptSummaryResponse> = emptyList(),
    val stores: List<StoreResponse> = emptyList(),
    val selectedStoreId: String? = null,
    val isLoading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class HistoryViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(HistoryUiState())
    val uiState: StateFlow<HistoryUiState> = _uiState.asStateFlow()

    init {
        loadStores()
        loadReceipts()
    }

    fun selectStore(storeId: String?) {
        _uiState.update { it.copy(selectedStoreId = storeId) }
        loadReceipts()
    }

    fun refresh() {
        loadReceipts()
    }

    private fun loadStores() {
        viewModelScope.launch {
            try {
                val response = receiptRepository.listStores()
                _uiState.update { it.copy(stores = response.items) }
            } catch (_: Exception) {
                // Store filter is optional
            }
        }
    }

    private fun loadReceipts() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val response = receiptRepository.listReceiptsFiltered(
                    storeId = _uiState.value.selectedStoreId,
                    status = "CONFIRMED",
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        receipts = response.items,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = e.message ?: "Kunne ikke hente historikk",
                    )
                }
            }
        }
    }
}
