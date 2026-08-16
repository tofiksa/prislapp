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
import no.prislapp.data.remote.dto.ReceiptConfirmItemRequest
import no.prislapp.data.remote.dto.ReceiptConfirmRequest
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.repository.ReceiptRepository
import java.math.BigDecimal
import java.util.UUID
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

data class EditableReceiptItem(
    val localId: String = UUID.randomUUID().toString(),
    val serverId: String? = null,
    val name: String = "",
    val quantity: String = "1",
    val unitPrice: String = "",
    val lineTotal: String = "",
)

data class ReceiptReviewUiState(
    val isLoading: Boolean = true,
    val isSaving: Boolean = false,
    val isReadOnly: Boolean = false,
    val receiptId: String = "",
    val storeName: String = "",
    val total: String = "",
    val items: List<EditableReceiptItem> = emptyList(),
    val isConfirmed: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class ReceiptReviewViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val receiptId: String = checkNotNull(savedStateHandle["receiptId"])

    private val _uiState = MutableStateFlow(ReceiptReviewUiState(receiptId = receiptId))
    val uiState: StateFlow<ReceiptReviewUiState> = _uiState.asStateFlow()

    init {
        loadReceipt()
    }

    private fun loadReceipt() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val receipt = receiptRepository.getReceiptDetail(receiptId)
                _uiState.update { it.copy(isLoading = false, isReadOnly = receipt.status == "CONFIRMED") }
                applyReceipt(receipt)
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

    private fun applyReceipt(receipt: ReceiptDetailResponse) {
        _uiState.update {
            it.copy(
                storeName = receipt.store?.name.orEmpty(),
                total = receipt.total?.toPlainString().orEmpty(),
                items = receipt.items.map { item ->
                    EditableReceiptItem(
                        serverId = item.id,
                        name = item.raw_product_name,
                        quantity = item.quantity.toPlainString(),
                        unitPrice = item.unit_price?.toPlainString().orEmpty(),
                        lineTotal = item.line_total.toPlainString(),
                    )
                },
            )
        }
    }

    fun updateStoreName(value: String) {
        _uiState.update { it.copy(storeName = value) }
    }

    fun updateTotal(value: String) {
        _uiState.update { it.copy(total = value) }
    }

    fun updateItem(localId: String, transform: (EditableReceiptItem) -> EditableReceiptItem) {
        _uiState.update { state ->
            state.copy(
                items = state.items.map { item ->
                    if (item.localId == localId) transform(item) else item
                },
            )
        }
    }

    fun addItem() {
        _uiState.update {
            it.copy(items = it.items + EditableReceiptItem())
        }
    }

    fun removeItem(localId: String) {
        _uiState.update {
            it.copy(items = it.items.filterNot { item -> item.localId == localId })
        }
    }

    fun confirmReceipt() {
        val state = _uiState.value
        if (state.items.isEmpty()) {
            _uiState.update { it.copy(error = "Legg til minst én varelinje") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null) }
            try {
                val request = ReceiptConfirmRequest(
                    store_name = state.storeName.ifBlank { null },
                    total = state.total.toBigDecimalOrNull(),
                    items = state.items.map { item ->
                        ReceiptConfirmItemRequest(
                            id = item.serverId,
                            raw_product_name = item.name,
                            quantity = item.quantity.toBigDecimalOrNull() ?: BigDecimal.ONE,
                            unit_price = item.unitPrice.toBigDecimalOrNull(),
                            line_total = item.lineTotal.toBigDecimalOrNull()
                                ?: throw IllegalArgumentException("Ugyldig linjepris for ${item.name}"),
                        )
                    },
                )
                val receipt = receiptRepository.confirmReceipt(receiptId, request)
                applyReceipt(receipt)
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        isReadOnly = true,
                        isConfirmed = true,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        error = e.message ?: "Kunne ikke bekrefte kvittering",
                    )
                }
            }
        }
    }
}
