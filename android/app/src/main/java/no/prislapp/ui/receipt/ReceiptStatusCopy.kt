package no.prislapp.ui.receipt

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import no.prislapp.R
import no.prislapp.data.local.entity.ReceiptQueueStatus

fun receiptStatusLabelRes(status: String): Int = when (status) {
    "queued_offline", "PENDING" -> R.string.status_queued_offline
    "uploading", "UPLOADING" -> R.string.status_uploading
    "processing", "PROCESSING", "UPLOADED" -> R.string.status_processing
    "ready_for_review", "READY_FOR_REVIEW" -> R.string.status_ready
    "needs_action", "FAILED" -> R.string.status_needs_action
    "failed_permanent" -> R.string.status_failed_permanent
    "CONFIRMED" -> R.string.status_confirmed
    else -> R.string.status_unknown
}

fun showProcessingScreenRetry(status: String, serverReceiptId: String?, error: String?): Boolean {
    if (ReceiptQueueStatus.canRetry(status, serverReceiptId)) {
        return true
    }
    val canonical = ReceiptQueueStatus.canonical(status, serverReceiptId)
    return error != null && canonical == ReceiptQueueStatus.PROCESSING
}

@Composable
fun receiptStatusLabel(status: String): String {
    val res = receiptStatusLabelRes(status)
    return if (res == R.string.status_unknown) {
        stringResource(res, status)
    } else {
        stringResource(res)
    }
}
