package no.prislapp.data.upload

import kotlinx.coroutines.CancellationException
import no.prislapp.data.local.entity.PendingReceiptEntity

enum class DrainOutcome {
    SUCCESS,
    RETRY,
}

suspend fun drainReceiptUploads(
    pending: List<PendingReceiptEntity>,
    upload: suspend (PendingReceiptEntity) -> Unit,
    markPermanent: suspend (PendingReceiptEntity, String?) -> Unit,
    onRetryable: suspend (PendingReceiptEntity, String?) -> Unit,
    onAuthPause: () -> Unit,
): DrainOutcome {
    var needsRetry = false
    for (entity in pending) {
        try {
            upload(entity)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val code = UploadErrorClassifier.errorCode(e)
            when (UploadErrorClassifier.classify(e)) {
                UploadErrorKind.PERMANENT -> markPermanent(entity, code)
                UploadErrorKind.RETRYABLE -> {
                    onRetryable(entity, code)
                    needsRetry = true
                }
                UploadErrorKind.AUTH_PAUSE -> {
                    onAuthPause()
                    return DrainOutcome.SUCCESS
                }
            }
        }
    }
    return if (needsRetry) DrainOutcome.RETRY else DrainOutcome.SUCCESS
}
