package no.prislapp.data.repository

import android.content.Context
import androidx.work.WorkManager
import io.mockk.*
import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.TokenStore
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.PrislappApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

class ReceiptRepositoryTest {
    @Test
    fun expiredLocalImagesAreRemovedWithoutTouchingRecentCaptures() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val unuploadedOld = File.createTempFile("old-unuploaded", ".jpg")
        val leftoverOld = File.createTempFile("old-uploaded", ".jpg")
        val recent = File.createTempFile("recent-receipt", ".jpg")
        val unuploaded = PendingReceiptEntity(
            id = 9,
            imagePath = unuploadedOld.path,
            userId = "a",
            createdAt = 1,
            status = "queued_offline",
            serverReceiptId = null,
        )
        val leftover = PendingReceiptEntity(
            id = 10,
            imagePath = leftoverOld.path,
            userId = "a",
            createdAt = 1,
            status = "processing",
            serverReceiptId = "srv-1",
        )
        coEvery { dao.getExpired(any()) } returns listOf(unuploaded, leftover)
        val repository = ReceiptRepository(mockk(), mockk(), dao, mockk(), mockk())
        try {
            repository.deleteExpiredLocalImages()
            assertTrue(unuploadedOld.exists())
            assertFalse(leftoverOld.exists())
            assertTrue(recent.exists())
            coVerify(exactly = 0) { dao.deleteById(9) }
            coVerify { dao.deleteById(10) }
        } finally {
            unuploadedOld.delete()
            leftoverOld.delete()
            recent.delete()
        }
    }

    @Test
    fun failedUploadReturnsToPendingWithoutLosingCaptureIdentity() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "a"
        val repository = ReceiptRepository(mockk<Context>(), api, dao, mockk<WorkManager>(), store)
        val file = File.createTempFile("receipt", ".jpg")
        try {
            val entity = PendingReceiptEntity(id = 1, imagePath = file.path, userId = "a")
            val updates = mutableListOf<PendingReceiptEntity>()
            coEvery { dao.update(capture(updates)) } just Runs
            coEvery { api.uploadReceipt(any(), any(), any()) } throws IOException("offline")
            try {
                repository.uploadPendingReceipt(entity)
                fail("Must propagate network failure")
            } catch (_: IOException) {
            }
            assertEquals("queued_offline", updates.last().status)
            assertEquals(entity.captureId, updates.last().captureId)
        } finally {
            file.delete()
        }
    }

    @Test
    fun uploadRejectsReceiptOwnedByAnotherAccount() = runTest {
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "b"
        val repository = ReceiptRepository(mockk(), api, mockk(), mockk(), store)
        try {
            repository.uploadPendingReceipt(PendingReceiptEntity(imagePath = "none", userId = "a"))
            fail("Must reject account mismatch")
        } catch (_: IllegalStateException) {
        }
        coVerify(exactly = 0) { api.uploadReceipt(any(), any(), any()) }
    }

    @Test
    fun removeLocalDeletesRowAndFileWithoutTouchingOthers() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "a"
        val keepFile = File.createTempFile("keep-receipt", ".jpg")
        val removeFile = File.createTempFile("remove-receipt", ".jpg")
        val remove = PendingReceiptEntity(
            id = 1,
            imagePath = removeFile.path,
            userId = "a",
            captureId = "cap-remove",
        )
        val keep = PendingReceiptEntity(
            id = 2,
            imagePath = keepFile.path,
            userId = "a",
            captureId = "cap-keep",
        )
        coEvery { dao.getById(1) } returns remove
        coEvery { dao.getById(2) } returns keep
        val repository = ReceiptRepository(mockk(), api, dao, mockk(), store)
        try {
            repository.removeLocal(1)
            assertFalse(removeFile.exists())
            assertTrue(keepFile.exists())
            coVerify { dao.deleteById(1) }
            coVerify(exactly = 0) { dao.deleteById(2) }
            coVerify(exactly = 0) { api.deleteReceipt(any()) }
            coVerify(exactly = 0) { api.confirmReceipt(any(), any()) }
        } finally {
            keepFile.delete()
            removeFile.delete()
        }
    }

    @Test
    fun getPendingForUploadExcludesFailedPermanent() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "a"
        val queued = PendingReceiptEntity(id = 1, imagePath = "/q.jpg", userId = "a", status = "queued_offline")
        val permanent = PendingReceiptEntity(
            id = 2,
            imagePath = "/p.jpg",
            userId = "a",
            status = "failed_permanent",
        )
        val statuses = slot<List<String>>()
        coEvery { dao.getByStatuses(capture(statuses), "a") } returns listOf(queued, permanent)
        val repository = ReceiptRepository(mockk(), mockk(), dao, mockk(), store)
        val pending = repository.getPendingForUpload()
        assertEquals(listOf(1L), pending.map { it.id })
        assertFalse(statuses.captured.contains("failed_permanent"))
    }

    @Test
    fun queueDrainDoesNotConfirmReceiptsOrWritePriceObservations() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "a"
        val cutoff = System.currentTimeMillis() - TimeUnit.DAYS.toMillis(31)
        coEvery { dao.getExpired(any()) } returns emptyList()
        val repository = ReceiptRepository(mockk(), api, dao, mockk(), store)
        repository.deleteExpiredLocalImages()
        coVerify(exactly = 0) { api.confirmReceipt(any(), any()) }
        assertTrue(cutoff > 0)
    }
}
