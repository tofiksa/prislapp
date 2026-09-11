package no.prislapp.data.repository

import android.content.Context
import android.net.Uri
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.prislapp.data.local.TokenStore
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.local.entity.ReceiptQueueStatus
import no.prislapp.data.local.entity.canonicalStatus
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ReceiptConfirmRequest
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.remote.dto.ReceiptListResponse
import no.prislapp.data.remote.dto.ReceiptUploadResponse
import no.prislapp.data.remote.dto.StoreListResponse
import no.prislapp.worker.ReceiptPollWorker
import no.prislapp.worker.ReceiptUploadWorker
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.io.FileNotFoundException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ReceiptRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: PrislappApi,
    private val pendingReceiptDao: PendingReceiptDao,
    private val workManager: androidx.work.WorkManager,
    private val tokenStore: TokenStore,
) {
    @Volatile
    private var uploadQueuePaused: Boolean = false

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    fun observePendingReceipts(): Flow<List<PendingReceiptEntity>> {
        return tokenStore.userId.flatMapLatest { user ->
            if (user == null) flowOf(emptyList()) else pendingReceiptDao.observeAll(user)
        }
    }

    suspend fun queueReceiptCapture(imageFile: File): Long {
        val entity = PendingReceiptEntity(
            imagePath = imageFile.absolutePath,
            userId = checkNotNull(tokenStore.getUserId()) { "Logg inn før du tar bilde" },
            status = PendingReceiptEntity.STATUS_QUEUED_OFFLINE,
        )
        val id = pendingReceiptDao.insert(entity)
        ReceiptUploadWorker.enqueue(workManager)
        return id
    }

    suspend fun getPendingReceipt(id: Long): PendingReceiptEntity? {
        return pendingReceiptDao.getById(id)?.takeIf { it.userId == tokenStore.getUserId() }
    }

    suspend fun getPendingReceiptByServerId(serverReceiptId: String): PendingReceiptEntity? {
        return pendingReceiptDao.getByServerReceiptId(serverReceiptId)
            ?.takeIf { it.userId == tokenStore.getUserId() }
    }

    suspend fun getReceiptDetail(receiptId: String): ReceiptDetailResponse {
        return api.getReceipt(receiptId)
    }

    suspend fun listReceipts(page: Int = 1): ReceiptListResponse {
        return api.listReceipts(page)
    }

    suspend fun listReceiptsFiltered(
        page: Int = 1,
        storeId: String? = null,
        status: String? = null,
        fromDate: String? = null,
        toDate: String? = null,
    ): ReceiptListResponse {
        return api.listReceipts(
            page = page,
            storeId = storeId,
            status = status,
            fromDate = fromDate,
            toDate = toDate,
        )
    }

    suspend fun confirmReceipt(
        receiptId: String,
        request: ReceiptConfirmRequest,
    ): ReceiptDetailResponse {
        val response = api.confirmReceipt(receiptId, request)
        syncLocalStatus(receiptId, response.status)
        return response
    }

    suspend fun deleteReceipt(receiptId: String) {
        api.deleteReceipt(receiptId)
        pendingReceiptDao.getByServerReceiptId(receiptId)?.let {
            withContext(Dispatchers.IO) { File(it.imagePath).delete() }
            pendingReceiptDao.deleteById(it.id)
        }
    }

    suspend fun removeLocal(localId: Long) {
        val entity = getPendingReceipt(localId) ?: return
        withContext(Dispatchers.IO) { File(entity.imagePath).delete() }
        pendingReceiptDao.deleteById(entity.id)
    }

    suspend fun listStores(): StoreListResponse {
        return api.listStores()
    }

    suspend fun uploadPendingReceipt(entity: PendingReceiptEntity): ReceiptUploadResponse {
        check(entity.userId == tokenStore.getUserId()) { "Kontoen er endret" }
        val file = File(entity.imagePath)
        if (!file.exists()) throw FileNotFoundException(entity.imagePath)

        pendingReceiptDao.update(
            entity.copy(status = PendingReceiptEntity.STATUS_UPLOADING, lastErrorCode = null),
        )

        val requestBody = file.asRequestBody("image/jpeg".toMediaType())
        val part = MultipartBody.Part.createFormData("file", file.name, requestBody)
        val response = try {
            api.uploadReceipt(part, entity.captureId, entity.userId)
        } catch (e: Exception) {
            withContext(kotlinx.coroutines.NonCancellable) {
                pendingReceiptDao.update(
                    entity.copy(
                        status = PendingReceiptEntity.STATUS_QUEUED_OFFLINE,
                        lastErrorCode = no.prislapp.data.upload.UploadErrorClassifier.errorCode(e),
                    ),
                )
            }
            throw e
        }

        val localStatus = ReceiptQueueStatus.fromServer(response.status, response.id)
        pendingReceiptDao.update(
            entity.copy(
                serverReceiptId = response.id,
                status = localStatus,
                lastErrorCode = null,
            ),
        )
        ReceiptPollWorker.enqueue(workManager, response.id, entity.id)
        withContext(Dispatchers.IO) { file.delete() }
        return response
    }

    suspend fun syncLocalStatus(serverReceiptId: String, status: String) {
        val entity = pendingReceiptDao.getByServerReceiptId(serverReceiptId) ?: return
        if (entity.userId != tokenStore.getUserId()) return
        pendingReceiptDao.update(
            entity.copy(status = ReceiptQueueStatus.fromServer(status, serverReceiptId)),
        )
    }

    suspend fun getPendingForUpload(): List<PendingReceiptEntity> {
        if (uploadQueuePaused) return emptyList()
        val userId = tokenStore.getUserId() ?: return emptyList()
        return pendingReceiptDao.getByStatuses(
            listOf(
                PendingReceiptEntity.STATUS_QUEUED_OFFLINE,
                PendingReceiptEntity.STATUS_PENDING,
                PendingReceiptEntity.STATUS_UPLOADING,
                PendingReceiptEntity.STATUS_UPLOADING_LEGACY,
            ),
            userId,
        ).filter { ReceiptQueueStatus.isPendingUpload(it.status, it.serverReceiptId) }
    }

    suspend fun getPendingForPoll(): List<PendingReceiptEntity> {
        return pendingReceiptDao.getByStatuses(
            listOf(
                PendingReceiptEntity.STATUS_PROCESSING,
                PendingReceiptEntity.STATUS_PROCESSING_LEGACY,
                PendingReceiptEntity.STATUS_UPLOADED,
            ),
            tokenStore.getUserId() ?: return emptyList(),
        )
    }

    suspend fun retryReceipt(localId: Long) {
        val entity = getPendingReceipt(localId) ?: error("Kvittering ikke funnet")
        uploadQueuePaused = false
        val canonical = ReceiptQueueStatus.canonical(entity.status, entity.serverReceiptId)
        when {
            canonical == ReceiptQueueStatus.NEEDS_ACTION && entity.serverReceiptId != null -> {
                val response = api.retryReceipt(entity.serverReceiptId)
                pendingReceiptDao.update(
                    entity.copy(status = ReceiptQueueStatus.fromServer(response.status, response.id)),
                )
                ReceiptPollWorker.enqueue(workManager, response.id, entity.id)
            }
            canonical == ReceiptQueueStatus.QUEUED_OFFLINE || entity.serverReceiptId == null -> {
                pendingReceiptDao.update(
                    entity.copy(status = PendingReceiptEntity.STATUS_QUEUED_OFFLINE, lastErrorCode = null),
                )
                ReceiptUploadWorker.enqueue(workManager)
            }
        }
    }

    suspend fun retryServerReceipt(receiptId: String) {
        val response = api.retryReceipt(receiptId)
        syncLocalStatus(receiptId, response.status)
        ReceiptPollWorker.enqueueBackground(workManager)
    }

    fun pauseUploadQueue() {
        uploadQueuePaused = true
    }

    fun isUploadQueuePaused(): Boolean = uploadQueuePaused

    suspend fun markFailedPermanent(entity: PendingReceiptEntity, errorCode: String?) {
        pendingReceiptDao.update(
            entity.copy(status = PendingReceiptEntity.STATUS_FAILED_PERMANENT, lastErrorCode = errorCode),
        )
    }

    suspend fun markQueuedOffline(entity: PendingReceiptEntity, errorCode: String?) {
        pendingReceiptDao.update(
            entity.copy(status = PendingReceiptEntity.STATUS_QUEUED_OFFLINE, lastErrorCode = errorCode),
        )
    }

    fun resumePendingWork() {
        uploadQueuePaused = false
        ReceiptUploadWorker.enqueue(workManager)
        ReceiptPollWorker.enqueueBackground(workManager)
        no.prislapp.worker.ReceiptCleanupWorker.enqueue(workManager)
    }

    suspend fun deleteExpiredLocalImages() {
        val cutoff = System.currentTimeMillis() - java.util.concurrent.TimeUnit.DAYS.toMillis(30)
        for (entity in pendingReceiptDao.getExpired(cutoff)) {
            if (entity.serverReceiptId == null) continue
            val status = entity.canonicalStatus()
            if (status == ReceiptQueueStatus.QUEUED_OFFLINE ||
                status == ReceiptQueueStatus.FAILED_PERMANENT
            ) {
                continue
            }
            withContext(Dispatchers.IO) {
                val file = File(entity.imagePath)
                check(!file.exists() || file.delete()) { "Kunne ikke slette utløpt bilde" }
            }
            pendingReceiptDao.deleteById(entity.id)
        }
    }

    fun createReceiptImageFile(): File {
        val dir = File(context.filesDir, "receipts").apply { mkdirs() }
        return File(dir, "receipt_${System.currentTimeMillis()}.jpg")
    }

    fun copyReceiptImageFromUri(sourceUri: Uri): File {
        val destFile = createReceiptImageFile()
        context.contentResolver.openInputStream(sourceUri)?.use { input ->
            destFile.outputStream().use { output -> input.copyTo(output) }
        } ?: error("Kunne ikke lese bilde fra galleri")
        return destFile
    }
}
