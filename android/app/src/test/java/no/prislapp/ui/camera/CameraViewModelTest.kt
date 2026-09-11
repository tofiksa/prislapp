package no.prislapp.ui.camera

import android.graphics.Bitmap
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import no.prislapp.R
import no.prislapp.data.repository.ReceiptRepository
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(AndroidJUnit4::class)
class CameraViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun cleanup() {
        Dispatchers.resetMain()
    }

    @Test
    fun cameraFailureIsVisibleAndAllowsRetry() {
        val vm = CameraViewModel(mockk<ReceiptRepository>())
        vm.onCaptureError("Kamera utilgjengelig")
        assertEquals("Kamera utilgjengelig", vm.uiState.value.error)
        assertFalse(vm.uiState.value.isSaving)
    }

    @Test
    fun onPhotoCapturedSetsPreviewAndDoesNotQueueUntilAccept() = runTest {
        val repo = mockk<ReceiptRepository>()
        coEvery { repo.queueReceiptCapture(any()) } returns 42L
        val file = miniatureJpeg()
        val vm = CameraViewModel(repo, dispatcher)
        try {
            vm.onPhotoCaptured(file)
            advanceUntilIdle()
            coVerify(exactly = 0) { repo.queueReceiptCapture(any()) }
            assertEquals(file, vm.uiState.value.previewFile)
            assertFalse(vm.uiState.value.isSaving)

            vm.acceptPreview()
            advanceUntilIdle()
            coVerify(exactly = 1) { repo.queueReceiptCapture(file) }
            assertEquals(42L, vm.uiState.value.savedLocalId)
            assertNull(vm.uiState.value.previewFile)
        } finally {
            file.delete()
        }
    }

    @Test
    fun retakeDeletesTempFileAndDoesNotQueue() = runTest {
        val repo = mockk<ReceiptRepository>()
        coEvery { repo.queueReceiptCapture(any()) } returns 1L
        val file = miniatureJpeg()
        val vm = CameraViewModel(repo, dispatcher)
        vm.onPhotoCaptured(file)
        advanceUntilIdle()
        vm.retake()
        advanceUntilIdle()
        coVerify(exactly = 0) { repo.queueReceiptCapture(any()) }
        assertNull(vm.uiState.value.previewFile)
        assertFalse(file.exists())
    }

    @Test
    fun rejectedGalleryFormatSetsErrorWithoutQueue() = runTest {
        val repo = mockk<ReceiptRepository>()
        val pdf = File.createTempFile("receipt", ".pdf").apply { writeText("%PDF-1.4\n") }
        every { repo.copyReceiptImageFromUri(any()) } returns pdf
        coEvery { repo.queueReceiptCapture(any()) } returns 1L
        val vm = CameraViewModel(repo, dispatcher)
        try {
            vm.onGalleryImageSelected(Uri.parse("content://media/external/1"))
            advanceUntilIdle()
            coVerify(exactly = 0) { repo.queueReceiptCapture(any()) }
            assertFalse(vm.uiState.value.isSaving)
            assertNull(vm.uiState.value.previewFile)
            assertEquals(R.string.receipt_image_unsupported_format, vm.uiState.value.errorResId)
            assertFalse(pdf.exists())
        } finally {
            pdf.delete()
        }
    }

    @Test
    fun galleryImportWorksWithOnlyRepository() = runTest {
        val repo = mockk<ReceiptRepository>()
        val file = miniatureJpeg()
        every { repo.copyReceiptImageFromUri(any()) } returns file
        coEvery { repo.queueReceiptCapture(any()) } returns 9L
        val vm = CameraViewModel(repo, dispatcher)
        try {
            vm.onGalleryImageSelected(Uri.parse("content://media/external/2"))
            advanceUntilIdle()
            assertEquals(file, vm.uiState.value.previewFile)
            coVerify(exactly = 0) { repo.queueReceiptCapture(any()) }
            assertFalse(vm.uiState.value.isSaving)
        } finally {
            file.delete()
        }
    }

    private fun miniatureJpeg(): File {
        val bitmap = Bitmap.createBitmap(4, 4, Bitmap.Config.ARGB_8888)
        val file = File.createTempFile("camera-preview", ".jpg")
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        return file
    }
}
