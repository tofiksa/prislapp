package no.prislapp.ui.home

import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.dto.ReceiptSummaryResponse

data class HomeUiState(
    val isLoading: Boolean = false,
    val pendingReceipts: List<PendingReceiptEntity> = emptyList(),
    val serverReceipts: List<ReceiptSummaryResponse> = emptyList(),
    val error: String? = null,
)
