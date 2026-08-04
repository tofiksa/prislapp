package no.prislapp.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.delay
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.repository.ReceiptRepository

@HiltWorker
class ReceiptPollWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val receiptRepository: ReceiptRepository,
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        val serverReceiptId = inputData.getString(KEY_SERVER_RECEIPT_ID)
        val localId = inputData.getLong(KEY_LOCAL_ID, -1L)

        if (serverReceiptId != null) {
            return pollSingle(serverReceiptId, localId)
        }

        val pending = receiptRepository.getPendingForPoll()
        for (entity in pending) {
            val receiptId = entity.serverReceiptId ?: continue
            pollSingle(receiptId, entity.id)
        }
        return Result.success()
    }

    private suspend fun pollSingle(serverReceiptId: String, localId: Long): Result {
        repeat(MAX_ACTIVE_POLLS) {
            try {
                val detail = receiptRepository.getReceiptDetail(serverReceiptId)
                receiptRepository.syncLocalStatus(serverReceiptId, detail.status)
                when (detail.status) {
                    PendingReceiptEntity.STATUS_READY_FOR_REVIEW,
                    PendingReceiptEntity.STATUS_FAILED,
                    -> return Result.success()
                    else -> delay(POLL_INTERVAL_MS)
                }
            } catch (_: Exception) {
                delay(POLL_INTERVAL_MS)
            }
        }
        enqueueBackground(workManager = WorkManager.getInstance(applicationContext))
        return Result.success()
    }

    companion object {
        private const val WORK_NAME = "receipt_poll"
        private const val KEY_SERVER_RECEIPT_ID = "server_receipt_id"
        private const val KEY_LOCAL_ID = "local_id"
        private const val POLL_INTERVAL_MS = 3_000L
        private const val MAX_ACTIVE_POLLS = 40

        fun enqueue(workManager: WorkManager, serverReceiptId: String, localId: Long) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<ReceiptPollWorker>()
                .setConstraints(constraints)
                .setInputData(
                    workDataOf(
                        KEY_SERVER_RECEIPT_ID to serverReceiptId,
                        KEY_LOCAL_ID to localId,
                    ),
                )
                .build()
            workManager.enqueueUniqueWork(
                "$WORK_NAME-$serverReceiptId",
                ExistingWorkPolicy.REPLACE,
                request,
            )
        }

        fun enqueueBackground(workManager: WorkManager) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<ReceiptPollWorker>()
                .setConstraints(constraints)
                .build()
            workManager.enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
