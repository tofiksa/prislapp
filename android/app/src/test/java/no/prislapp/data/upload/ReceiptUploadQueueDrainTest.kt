package no.prislapp.data.upload

import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.entity.PendingReceiptEntity
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException

class ReceiptUploadQueueDrainTest {
    @Test
    fun permanentHeadOfLineDoesNotBlockLaterUploads() = runTest {
        val missing = PendingReceiptEntity(id = 1, imagePath = "/no-such-receipt.jpg", userId = "a")
        val secondFile = File.createTempFile("receipt-ok-2", ".jpg")
        val thirdFile = File.createTempFile("receipt-ok-3", ".jpg")
        val second = PendingReceiptEntity(id = 2, imagePath = secondFile.path, userId = "a")
        val third = PendingReceiptEntity(id = 3, imagePath = thirdFile.path, userId = "a")
        val uploaded = mutableListOf<Long>()
        val statuses = mutableMapOf<Long, String>()
        try {
            val outcome = drainReceiptUploads(
                pending = listOf(missing, second, third),
                upload = { entity ->
                    if (!File(entity.imagePath).exists()) throw FileNotFoundException(entity.imagePath)
                    uploaded += entity.id
                },
                markPermanent = { entity, _ ->
                    statuses[entity.id] = "failed_permanent"
                },
                onRetryable = { entity, _ ->
                    statuses[entity.id] = "queued_offline"
                },
                onAuthPause = { },
            )
            assertEquals(DrainOutcome.SUCCESS, outcome)
            assertEquals("failed_permanent", statuses[1])
            assertEquals(listOf(2L, 3L), uploaded)
        } finally {
            secondFile.delete()
            thirdFile.delete()
        }
    }

    @Test
    fun retryableItemContinuesQueueAndRequestsRetry() = runTest {
        val firstFile = File.createTempFile("receipt-retry", ".jpg")
        val secondFile = File.createTempFile("receipt-ok", ".jpg")
        try {
            val first = PendingReceiptEntity(id = 1, imagePath = firstFile.path, userId = "a")
            val second = PendingReceiptEntity(id = 2, imagePath = secondFile.path, userId = "a")
            val uploaded = mutableListOf<Long>()
            val outcome = drainReceiptUploads(
                pending = listOf(first, second),
                upload = { entity ->
                    if (entity.id == 1L) throw IOException("offline")
                    uploaded += entity.id
                },
                markPermanent = { _, _ -> },
                onRetryable = { _, _ -> },
                onAuthPause = { },
            )
            assertEquals(DrainOutcome.RETRY, outcome)
            assertEquals(listOf(2L), uploaded)
        } finally {
            firstFile.delete()
            secondFile.delete()
        }
    }

    @Test
    fun authPauseStopsRemainingUploadsAndDoesNotRetry() = runTest {
        val first = PendingReceiptEntity(id = 1, imagePath = "/a.jpg", userId = "a")
        val second = PendingReceiptEntity(id = 2, imagePath = "/b.jpg", userId = "a")
        val uploaded = mutableListOf<Long>()
        var paused = false
        val outcome = drainReceiptUploads(
            pending = listOf(first, second),
            upload = { entity ->
                uploaded += entity.id
                throw http(401)
            },
            markPermanent = { _, _ -> },
            onRetryable = { _, _ -> },
            onAuthPause = { paused = true },
        )
        assertTrue(paused)
        assertEquals(DrainOutcome.SUCCESS, outcome)
        assertEquals(listOf(1L), uploaded)
    }

    private fun http(code: Int): HttpException {
        val body = """{"detail":"error"}""".toResponseBody("application/json".toMediaType())
        return HttpException(Response.error<Any>(code, body))
    }
}
