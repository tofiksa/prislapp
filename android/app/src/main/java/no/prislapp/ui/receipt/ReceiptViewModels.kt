package no.prislapp.ui.receipt

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.repository.ReceiptRepository
import javax.inject.Inject

data class ReceiptProcessingUiState(
    val localId: Long,
    val serverReceiptId: String? = null,
    val status: String = PendingReceiptEntity.STATUS_PENDING,
    val isPolling: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class ReceiptProcessingViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val localId: Long = checkNotNull(savedStateHandle["localId"])

    private val _uiState = MutableStateFlow(
        ReceiptProcessingUiState(localId = localId),
    )
    val uiState: StateFlow<ReceiptProcessingUiState> = _uiState.asStateFlow()

    init {
        startPolling()
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (isActive) {
                val pending = receiptRepository.getPendingReceipt(localId)
                if (pending == null) {
                    _uiState.update {
                        it.copy(isPolling = false, error = "Lokal kvittering ikke funnet")
                    }
                    break
                }

                _uiState.update {
                    it.copy(
                        status = pending.status,
                        serverReceiptId = pending.serverReceiptId,
                    )
                }

                val serverReceiptId = pending.serverReceiptId
                if (serverReceiptId != null) {
                    try {
                        val detail = receiptRepository.getReceiptDetail(serverReceiptId)
                        receiptRepository.syncLocalStatus(serverReceiptId, detail.status)
                        _uiState.update {
                            it.copy(status = detail.status, error = null)
                        }
                        if (detail.status == PendingReceiptEntity.STATUS_READY_FOR_REVIEW ||
                            detail.status == PendingReceiptEntity.STATUS_FAILED
                        ) {
                            _uiState.update { it.copy(isPolling = false) }
                            break
                        }
                    } catch (e: Exception) {
                        _uiState.update {
                            it.copy(error = e.message ?: "Polling feilet")
                        }
                    }
                }

                delay(POLL_INTERVAL_MS)
            }
        }
    }

    companion object {
        private const val POLL_INTERVAL_MS = 3_000L
    }
}

data class ReceiptReviewUiState(
    val isLoading: Boolean = true,
    val receipt: ReceiptDetailResponse? = null,
    val error: String? = null,
)

@HiltViewModel
class ReceiptReviewViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val receiptId: String = checkNotNull(savedStateHandle["receiptId"])

    private val _uiState = MutableStateFlow(ReceiptReviewUiState())
    val uiState: StateFlow<ReceiptReviewUiState> = _uiState.asStateFlow()

    init {
        loadReceipt()
    }

    private fun loadReceipt() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val receipt = receiptRepository.getReceiptDetail(receiptId)
                _uiState.update { it.copy(isLoading = false, receipt = receipt) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = e.message ?: "Kunne ikke hente kvittering",
                    )
                }
            }
        }
    }
}
