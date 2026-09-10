package no.prislapp.data.repository

import android.content.Context
import androidx.work.WorkManager
import io.mockk.*
import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.TokenStore
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.PrislappApi
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.io.IOException

class ReceiptRepositoryTest {
    @Test fun expiredLocalImagesAreRemovedWithoutTouchingRecentCaptures() = runTest {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val old = File.createTempFile("old-receipt", ".jpg")
        val recent = File.createTempFile("recent-receipt", ".jpg")
        val entity = PendingReceiptEntity(id = 9, imagePath = old.path, userId = "a", createdAt = 1)
        coEvery { dao.getExpired(any()) } returns listOf(entity)
        val repository = ReceiptRepository(mockk(), mockk(), dao, mockk(), mockk())
        try {
            repository.deleteExpiredLocalImages()
            assertFalse(old.exists())
            assertTrue(recent.exists())
            coVerify { dao.deleteById(9) }
        } finally { old.delete(); recent.delete() }
    }

    @Test fun failedUploadReturnsToPendingWithoutLosingCaptureIdentity() = runTest {
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
            try { repository.uploadPendingReceipt(entity); fail("Must propagate network failure") } catch (_: IOException) { }
            assertEquals("PENDING", updates.last().status)
            assertEquals(entity.captureId, updates.last().captureId)
        } finally { file.delete() }
    }

    @Test fun uploadRejectsReceiptOwnedByAnotherAccount() = runTest {
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "b"
        val repository = ReceiptRepository(mockk(), api, mockk(), mockk(), store)
        try {
            repository.uploadPendingReceipt(PendingReceiptEntity(imagePath = "none", userId = "a"))
            fail("Must reject account mismatch")
        } catch (_: IllegalStateException) { }
        coVerify(exactly = 0) { api.uploadReceipt(any(), any(), any()) }
    }
}
