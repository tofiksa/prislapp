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
import no.prislapp.BuildConfig
import no.prislapp.data.repository.ReceiptRepository
import java.math.BigDecimal
import java.util.UUID
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.ResolverStyle
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
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
    private var pollingJob: Job? = null

    init {
        startPolling()
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
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
                        status = no.prislapp.data.local.entity.ReceiptQueueStatus.canonical(
                            pending.status,
                            pending.serverReceiptId,
                        ),
                        serverReceiptId = pending.serverReceiptId,
                    )
                }

                val localStatus = no.prislapp.data.local.entity.ReceiptQueueStatus.canonical(
                    pending.status,
                    pending.serverReceiptId,
                )
                if (pending.status == PendingReceiptEntity.STATUS_CONFIRMED ||
                    localStatus == no.prislapp.data.local.entity.ReceiptQueueStatus.CONFIRMED
                ) {
                    _uiState.update { it.copy(isPolling = false) }
                    break
                }
                if (localStatus == no.prislapp.data.local.entity.ReceiptQueueStatus.FAILED_PERMANENT ||
                    localStatus == no.prislapp.data.local.entity.ReceiptQueueStatus.NEEDS_ACTION
                ) {
                    _uiState.update { it.copy(isPolling = false) }
                    break
                }

                val serverReceiptId = pending.serverReceiptId
                if (serverReceiptId != null) {
                    try {
                        val detail = receiptRepository.getReceiptDetail(serverReceiptId)
                        receiptRepository.syncLocalStatus(serverReceiptId, detail.status)
                        val mapped = no.prislapp.data.local.entity.ReceiptQueueStatus.fromServer(
                            detail.status,
                            serverReceiptId,
                        )
                        _uiState.update {
                            it.copy(status = mapped, error = null)
                        }
                        if (mapped == no.prislapp.data.local.entity.ReceiptQueueStatus.READY_FOR_REVIEW ||
                            mapped == no.prislapp.data.local.entity.ReceiptQueueStatus.NEEDS_ACTION ||
                            mapped == no.prislapp.data.local.entity.ReceiptQueueStatus.FAILED_PERMANENT
                        ) {
                            _uiState.update { it.copy(isPolling = false) }
                            break
                        }
                    } catch (e: CancellationException) { throw e
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

    fun retry() {
        viewModelScope.launch {
            try {
                receiptRepository.retryReceipt(localId)
                _uiState.update { it.copy(isPolling = true, error = null) }
                startPolling()
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _uiState.update { it.copy(error = e.message) } }
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
    val purchaseDate: String = "",
    val rawOcrText: String = "",
    val status: String = "",
    val isDeleted: Boolean = false,
    val localImagePath: String? = null,
    val imageUrl: String? = null,
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
                val localImagePath = receiptRepository.getPendingReceiptByServerId(receiptId)
                    ?.imagePath
                    ?.takeIf { java.io.File(it).exists() }
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        isReadOnly = receipt.status != "READY_FOR_REVIEW",
                        status = receipt.status,
                        localImagePath = localImagePath,
                        imageUrl = BuildConfig.API_BASE_URL + "receipts/$receiptId/image",
                    )
                }
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
                purchaseDate = receipt.purchase_date?.let { date ->
                    runCatching { OffsetDateTime.parse(date).atZoneSameInstant(ZoneId.of("Europe/Oslo")).toLocalDate().format(dateFormat) }
                        .getOrElse { date.take(10) }
                }.orEmpty(),
                rawOcrText = receipt.raw_ocr_text.orEmpty(),
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

    fun updatePurchaseDate(value: String) { _uiState.update { it.copy(purchaseDate = value) } }

    fun deleteReceipt() {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null) }
            try {
                receiptRepository.deleteReceipt(receiptId)
                _uiState.update { it.copy(isSaving = false, isDeleted = true) }
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _uiState.update { it.copy(isSaving = false, error = e.message) } }
        }
    }

    fun retryProcessing() {
        viewModelScope.launch {
            try {
                receiptRepository.retryServerReceipt(receiptId)
                loadReceipt()
            } catch (e: CancellationException) { throw e
            } catch (e: Exception) { _uiState.update { it.copy(error = e.message) } }
        }
    }

    fun reload() = loadReceipt()

    private fun decimal(value: String, label: String): BigDecimal =
        value.trim().replace(',', '.').toBigDecimalOrNull()
            ?.takeIf { it >= BigDecimal.ZERO } ?: throw IllegalArgumentException("Ugyldig $label")

    companion object {
        private val dateFormat = DateTimeFormatter.ofPattern("dd.MM.uuuu").withResolverStyle(ResolverStyle.STRICT)
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
        if (state.isSaving || state.isReadOnly) return
        if (state.items.isEmpty()) {
            _uiState.update { it.copy(error = "Legg til minst én varelinje") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null) }
            try {
                val request = ReceiptConfirmRequest(
                    store_name = state.storeName.ifBlank { null },
                    purchase_date = state.purchaseDate.takeIf { it.isNotBlank() }?.let {
                        LocalDate.parse(it, dateFormat).atStartOfDay(ZoneId.of("Europe/Oslo")).toInstant().toString()
                    },
                    total = state.total.takeIf { it.isNotBlank() }?.let { decimal(it, "total") },
                    items = state.items.map { item ->
                        ReceiptConfirmItemRequest(
                            id = item.serverId,
                            raw_product_name = item.name.trim().also { require(it.isNotBlank()) { "Varenavn mangler" } },
                            quantity = decimal(item.quantity, "antall").also { require(it > BigDecimal.ZERO) { "Antall må være større enn null" } },
                            unit_price = item.unitPrice.takeIf { it.isNotBlank() }?.let { decimal(it, "enhetspris") },
                            line_total = decimal(item.lineTotal, "linjepris for ${item.name}"),
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
