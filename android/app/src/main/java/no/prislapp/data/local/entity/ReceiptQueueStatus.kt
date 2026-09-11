package no.prislapp.data.local.entity

object ReceiptQueueStatus {
    const val QUEUED_OFFLINE = "queued_offline"
    const val UPLOADING = "uploading"
    const val PROCESSING = "processing"
    const val READY_FOR_REVIEW = "ready_for_review"
    const val NEEDS_ACTION = "needs_action"
    const val FAILED_PERMANENT = "failed_permanent"
    const val CONFIRMED = "CONFIRMED"

    fun canonical(status: String, serverReceiptId: String?): String = when (status) {
        "PENDING", QUEUED_OFFLINE -> QUEUED_OFFLINE
        "UPLOADING", UPLOADING -> UPLOADING
        "UPLOADED", "PROCESSING", PROCESSING -> PROCESSING
        "READY_FOR_REVIEW", READY_FOR_REVIEW -> READY_FOR_REVIEW
        FAILED_PERMANENT -> FAILED_PERMANENT
        NEEDS_ACTION -> NEEDS_ACTION
        "FAILED" -> if (serverReceiptId == null) FAILED_PERMANENT else NEEDS_ACTION
        "CONFIRMED", CONFIRMED -> CONFIRMED
        else -> status
    }

    fun fromServer(status: String, serverReceiptId: String?): String = canonical(status, serverReceiptId)

    fun isPendingUpload(status: String, serverReceiptId: String?): Boolean {
        val canonical = canonical(status, serverReceiptId)
        return canonical == QUEUED_OFFLINE || canonical == UPLOADING
    }

    fun canRetry(status: String, serverReceiptId: String?): Boolean {
        val canonical = canonical(status, serverReceiptId)
        return canonical == QUEUED_OFFLINE || (canonical == NEEDS_ACTION && serverReceiptId != null)
    }
}

fun PendingReceiptEntity.canonicalStatus(): String =
    ReceiptQueueStatus.canonical(status, serverReceiptId)

fun PendingReceiptEntity.canRetry(): Boolean =
    ReceiptQueueStatus.canRetry(status, serverReceiptId)
