package no.prislapp.ui.receipt

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import no.prislapp.R

fun receiptStatusLabelRes(status: String): Int = when (status) {
    "PENDING" -> R.string.status_pending
    "UPLOADING" -> R.string.status_uploading
    "UPLOADED" -> R.string.status_uploaded
    "PROCESSING" -> R.string.status_processing
    "READY_FOR_REVIEW" -> R.string.status_ready
    "FAILED" -> R.string.status_failed
    "CONFIRMED" -> R.string.status_confirmed
    else -> R.string.status_unknown
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
