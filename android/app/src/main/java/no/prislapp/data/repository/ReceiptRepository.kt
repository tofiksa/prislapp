package no.prislapp.data.repository

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.remote.dto.ReceiptListResponse
import no.prislapp.data.remote.dto.ReceiptUploadResponse
import no.prislapp.worker.ReceiptPollWorker
import no.prislapp.worker.ReceiptUploadWorker
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReceiptRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: PrislappApi,
    private val pendingReceiptDao: PendingReceiptDao,
    private val workManager: androidx.work.WorkManager,
) {
    fun observePendingReceipts(): Flow<List<PendingReceiptEntity>> {
        return pendingReceiptDao.observeAll()
    }

    suspend fun queueReceiptCapture(imageFile: File): Long {
        val entity = PendingReceiptEntity(imagePath = imageFile.absolutePath)
        val id = pendingReceiptDao.insert(entity)
        ReceiptUploadWorker.enqueue(workManager)
        return id
    }

    suspend fun getPendingReceipt(id: Long): PendingReceiptEntity? {
        return pendingReceiptDao.getById(id)
    }

    suspend fun getReceiptDetail(receiptId: String): ReceiptDetailResponse {
        return api.getReceipt(receiptId)
    }

    suspend fun listReceipts(page: Int = 1): ReceiptListResponse {
        return api.listReceipts(page)
    }

    suspend fun uploadPendingReceipt(entity: PendingReceiptEntity): ReceiptUploadResponse {
        val file = File(entity.imagePath)
        require(file.exists()) { "Image file not found: ${entity.imagePath}" }

        pendingReceiptDao.update(
            entity.copy(status = PendingReceiptEntity.STATUS_UPLOADING),
        )

        val requestBody = file.asRequestBody("image/jpeg".toMediaType())
        val part = MultipartBody.Part.createFormData("file", file.name, requestBody)
        val response = api.uploadReceipt(part)

        pendingReceiptDao.update(
            entity.copy(
                serverReceiptId = response.id,
                status = PendingReceiptEntity.STATUS_PROCESSING,
            ),
        )
        ReceiptPollWorker.enqueue(workManager, response.id, entity.id)
        return response
    }

    suspend fun syncLocalStatus(serverReceiptId: String, status: String) {
        val entity = pendingReceiptDao.getByServerReceiptId(serverReceiptId) ?: return
        pendingReceiptDao.update(entity.copy(status = status))
    }

    suspend fun getPendingForUpload(): List<PendingReceiptEntity> {
        return pendingReceiptDao.getByStatuses(
            listOf(
                PendingReceiptEntity.STATUS_PENDING,
                PendingReceiptEntity.STATUS_FAILED,
            ),
        )
    }

    suspend fun getPendingForPoll(): List<PendingReceiptEntity> {
        return pendingReceiptDao.getByStatuses(
            listOf(
                PendingReceiptEntity.STATUS_PROCESSING,
                PendingReceiptEntity.STATUS_UPLOADED,
            ),
        )
    }

    fun createReceiptImageFile(): File {
        val dir = File(context.filesDir, "receipts").apply { mkdirs() }
        return File(dir, "receipt_${System.currentTimeMillis()}.jpg")
    }
}
