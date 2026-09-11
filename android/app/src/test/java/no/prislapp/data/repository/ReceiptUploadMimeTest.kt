package no.prislapp.data.repository

import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.mockk.Runs
import io.mockk.coEvery
import io.mockk.just
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.TokenStore
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ReceiptUploadResponse
import okhttp3.MultipartBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ReceiptUploadMimeTest {
    @Test
    fun uploadPendingReceiptSendsPngContentTypeForPngFile() = runTest {
        assertEquals("image/png", uploadContentType(miniatureFile(Bitmap.CompressFormat.PNG, ".png")))
    }

    @Test
    fun uploadPendingReceiptSendsJpegContentTypeForJpegFile() = runTest {
        assertEquals("image/jpeg", uploadContentType(miniatureFile(Bitmap.CompressFormat.JPEG, ".jpg")))
    }

    @Test
    fun pngUploadMimeDoesNotDependOnJpgExtension() = runTest {
        val file = miniatureFile(Bitmap.CompressFormat.PNG, ".jpg")
        assertTrue(file.name.endsWith(".jpg"))
        assertEquals("image/png", uploadContentType(file))
    }

    private suspend fun uploadContentType(file: File): String {
        val dao = mockk<PendingReceiptDao>(relaxed = true)
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>()
        io.mockk.every { store.getUserId() } returns "a"
        coEvery { dao.update(any()) } just Runs
        val part = slot<MultipartBody.Part>()
        coEvery { api.uploadReceipt(capture(part), any(), any()) } returns ReceiptUploadResponse("srv", "PROCESSING")
        val repository = ReceiptRepository(mockk(), api, dao, mockk(relaxed = true), store)
        try {
            repository.uploadPendingReceipt(PendingReceiptEntity(id = 1, imagePath = file.path, userId = "a"))
            return checkNotNull(part.captured.body.contentType()).toString()
        } finally {
            file.delete()
        }
    }

    private fun miniatureFile(format: Bitmap.CompressFormat, suffix: String): File {
        val bitmap = Bitmap.createBitmap(2, 2, Bitmap.Config.ARGB_8888)
        val file = File.createTempFile("receipt-mime", suffix)
        file.outputStream().use { output ->
            check(bitmap.compress(format, 90, output))
        }
        return file
    }
}
