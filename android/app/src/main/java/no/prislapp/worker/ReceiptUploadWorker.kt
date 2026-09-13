package no.prislapp.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import no.prislapp.data.upload.DrainOutcome
import no.prislapp.data.upload.drainReceiptUploads
import no.prislapp.data.repository.ReceiptRepository
import java.util.concurrent.TimeUnit

@HiltWorker
class ReceiptUploadWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val receiptRepository: ReceiptRepository,
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        if (receiptRepository.isUploadQueuePaused()) return Result.success()
        val outcome = drainReceiptUploads(
            pending = receiptRepository.getPendingForUpload(),
            upload = { receiptRepository.uploadPendingReceipt(it) },
            markPermanent = { entity, code -> receiptRepository.markFailedPermanent(entity, code) },
            onRetryable = { entity, code -> receiptRepository.markQueuedOffline(entity, code) },
            onAuthPause = { receiptRepository.pauseUploadQueue() },
        )
        return when (outcome) {
            DrainOutcome.RETRY -> Result.retry()
            DrainOutcome.SUCCESS -> Result.success()
        }
    }

    companion object {
        private const val WORK_NAME = "receipt_upload"

        fun enqueue(workManager: WorkManager) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = OneTimeWorkRequestBuilder<ReceiptUploadWorker>()
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            workManager.enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.APPEND_OR_REPLACE,
                request,
            )
        }
    }
}
