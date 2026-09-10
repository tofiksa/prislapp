package no.prislapp.worker

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.CancellationException
import no.prislapp.data.repository.ReceiptRepository
import java.util.concurrent.TimeUnit

@HiltWorker
class ReceiptCleanupWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted parameters: WorkerParameters,
    private val repository: ReceiptRepository,
) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = try {
        repository.deleteExpiredLocalImages()
        Result.success()
    } catch (e: CancellationException) { throw e
    } catch (_: Exception) { Result.retry() }

    companion object {
        fun enqueue(manager: WorkManager) {
            manager.enqueueUniquePeriodicWork("receipt_cleanup", ExistingPeriodicWorkPolicy.KEEP,
                PeriodicWorkRequestBuilder<ReceiptCleanupWorker>(1, TimeUnit.HOURS).build())
        }
    }
}
