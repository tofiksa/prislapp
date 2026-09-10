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
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject

data class HistoryUiState(
    val receipts: List<ReceiptSummaryResponse> = emptyList(),
    val stores: List<StoreResponse> = emptyList(),
    val selectedStoreId: String? = null,
    val fromDate: LocalDate? = null,
    val toDate: LocalDate? = null,
    val isLoading: Boolean = true,
    val error: String? = null,
) {
    val fromDateLabel: String?
        get() = fromDate?.format(displayFormatter)

    val toDateLabel: String?
        get() = toDate?.format(displayFormatter)

    val hasDateFilter: Boolean
        get() = fromDate != null || toDate != null

    companion object {
        private val displayFormatter = DateTimeFormatter.ofPattern("dd.MM.yyyy", Locale("nb", "NO"))
    }
}

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

    fun setFromDate(date: LocalDate?) {
        _uiState.update { current ->
            val toDate = current.toDate
            current.copy(
                fromDate = date,
                toDate = if (date != null && toDate != null && toDate.isBefore(date)) date else toDate,
            )
        }
        loadReceipts()
    }

    fun setToDate(date: LocalDate?) {
        _uiState.update { current ->
            val fromDate = current.fromDate
            current.copy(
                toDate = date,
                fromDate = if (date != null && fromDate != null && fromDate.isAfter(date)) date else fromDate,
            )
        }
        loadReceipts()
    }

    fun clearDateFilter() {
        _uiState.update { it.copy(fromDate = null, toDate = null) }
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
                val state = _uiState.value
                val response = receiptRepository.listReceiptsFiltered(
                    storeId = state.selectedStoreId,
                    status = "CONFIRMED",
                    fromDate = state.fromDate?.toStartOfDayIso(),
                    toDate = state.toDate?.toEndOfDayIso(),
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

    private fun LocalDate.toStartOfDayIso(): String {
        return atStartOfDay(ZoneId.systemDefault()).toInstant().toString()
    }

    private fun LocalDate.toEndOfDayIso(): String {
        return atTime(23, 59, 59).atZone(ZoneId.systemDefault()).toInstant().toString()
    }
}
