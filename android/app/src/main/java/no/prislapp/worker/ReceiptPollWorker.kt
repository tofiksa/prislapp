package no.prislapp.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.CancellationException
import no.prislapp.data.repository.ReceiptRepository
import java.util.concurrent.TimeUnit

object PollSchedule {
    fun delaySeconds(failures: Int): Long = (30L * (1L shl failures.coerceIn(0, 4))).coerceAtMost(300L)
}

@HiltWorker
class ReceiptPollWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val receiptRepository: ReceiptRepository,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        val failures = inputData.getInt("failures", 0)
        var failed = false
        val pending = receiptRepository.getPendingForPoll()
        for (entity in pending) {
            val receiptId = entity.serverReceiptId ?: continue
            try {
                val detail = receiptRepository.getReceiptDetail(receiptId)
                receiptRepository.syncLocalStatus(receiptId, detail.status)
            } catch (e: CancellationException) { throw e
            } catch (_: Exception) { failed = true }
        }
        if (receiptRepository.getPendingForPoll().isNotEmpty()) {
            enqueueBackground(WorkManager.getInstance(applicationContext), if (failed) failures + 1 else 0)
        }
        return Result.success()
    }

    companion object {
        fun enqueue(workManager: WorkManager, serverReceiptId: String, localId: Long) {
            enqueueBackground(workManager)
        }

        fun enqueueBackground(workManager: WorkManager, failures: Int = 0) {
            val request = OneTimeWorkRequestBuilder<ReceiptPollWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setInitialDelay(PollSchedule.delaySeconds(failures), TimeUnit.SECONDS)
                .setInputData(workDataOf("failures" to failures))
                .build()
            workManager.enqueueUniqueWork("receipt_poll", ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
    }
}
