package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "pending_receipts")
data class PendingReceiptEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val imagePath: String,
    val serverReceiptId: String? = null,
    val status: String = STATUS_QUEUED_OFFLINE,
    val createdAt: Long = System.currentTimeMillis(),
    val userId: String = "",
    val captureId: String = java.util.UUID.randomUUID().toString(),
    val lastErrorCode: String? = null,
) {
    companion object {
        const val STATUS_PENDING = "PENDING"
        const val STATUS_QUEUED_OFFLINE = ReceiptQueueStatus.QUEUED_OFFLINE
        const val STATUS_UPLOADING = ReceiptQueueStatus.UPLOADING
        const val STATUS_UPLOADING_LEGACY = "UPLOADING"
        const val STATUS_UPLOADED = "UPLOADED"
        const val STATUS_PROCESSING = ReceiptQueueStatus.PROCESSING
        const val STATUS_PROCESSING_LEGACY = "PROCESSING"
        const val STATUS_READY_FOR_REVIEW = ReceiptQueueStatus.READY_FOR_REVIEW
        const val STATUS_READY_FOR_REVIEW_LEGACY = "READY_FOR_REVIEW"
        const val STATUS_FAILED = "FAILED"
        const val STATUS_NEEDS_ACTION = ReceiptQueueStatus.NEEDS_ACTION
        const val STATUS_FAILED_PERMANENT = ReceiptQueueStatus.FAILED_PERMANENT
        const val STATUS_CONFIRMED = ReceiptQueueStatus.CONFIRMED
    }
}
