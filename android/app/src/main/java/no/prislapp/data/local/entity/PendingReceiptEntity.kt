package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "pending_receipts")
data class PendingReceiptEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val imagePath: String,
    val serverReceiptId: String? = null,
    val status: String = STATUS_PENDING,
    val createdAt: Long = System.currentTimeMillis(),
) {
    companion object {
        const val STATUS_PENDING = "PENDING"
        const val STATUS_UPLOADING = "UPLOADING"
        const val STATUS_UPLOADED = "UPLOADED"
        const val STATUS_PROCESSING = "PROCESSING"
        const val STATUS_READY_FOR_REVIEW = "READY_FOR_REVIEW"
        const val STATUS_FAILED = "FAILED"
    }
}
