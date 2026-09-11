package no.prislapp.ui.receipt

import androidx.lifecycle.SavedStateHandle
import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import no.prislapp.BuildConfig
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.remote.dto.*
import no.prislapp.data.repository.ReceiptRepository
import org.junit.*
import org.junit.Assert.*
import java.io.File
import java.math.BigDecimal

@OptIn(ExperimentalCoroutinesApi::class)
class ReceiptReviewViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val repository = mockk<ReceiptRepository>()
    private val receipt = ReceiptDetailResponse("r", "READY_FOR_REVIEW", BigDecimal("25.90"),
        "2026-08-10T12:30:00Z", StoreResponse("s", "Kiwi", null), "2026-08-10T12:30:00Z", "OCR", listOf(
            ReceiptItemResponse("i", "Melk", BigDecimal.ONE, null, BigDecimal("25.90"))))
    @Before fun setup() {
        Dispatchers.setMain(dispatcher)
        coEvery { repository.getReceiptDetail("r") } returns receipt
        coEvery { repository.getPendingReceiptByServerId("r") } returns null
    }
    @After fun cleanup() { Dispatchers.resetMain() }

    @Test fun reviewSetsRemoteImageUrlAndLocalPathWhenFileExists() = runTest {
        val file = File.createTempFile("receipt", ".jpg")
        try {
            coEvery { repository.getPendingReceiptByServerId("r") } returns PendingReceiptEntity(
                imagePath = file.path,
                serverReceiptId = "r",
                userId = "u",
            )
            val vm = ReceiptReviewViewModel(SavedStateHandle(mapOf("receiptId" to "r")), repository)
            advanceUntilIdle()
            assertEquals(file.path, vm.uiState.value.localImagePath)
            assertEquals(BuildConfig.API_BASE_URL + "receipts/r/image", vm.uiState.value.imageUrl)
        } finally {
            file.delete()
        }
    }

    @Test fun reviewOmitsLocalPathWhenFileMissing() = runTest {
        coEvery { repository.getPendingReceiptByServerId("r") } returns PendingReceiptEntity(
            imagePath = "/tmp/does-not-exist-receipt.jpg",
            serverReceiptId = "r",
            userId = "u",
        )
        val vm = ReceiptReviewViewModel(SavedStateHandle(mapOf("receiptId" to "r")), repository)
        advanceUntilIdle()
        assertNull(vm.uiState.value.localImagePath)
        assertEquals(BuildConfig.API_BASE_URL + "receipts/r/image", vm.uiState.value.imageUrl)
    }

    @Test fun confirmationAcceptsNorwegianDecimalsAndEditedPurchaseDate() = runTest {
        val vm = ReceiptReviewViewModel(SavedStateHandle(mapOf("receiptId" to "r")), repository)
        advanceUntilIdle()
        vm.updatePurchaseDate("11.08.2026")
        vm.updateTotal("25,90")
        val item = vm.uiState.value.items.single()
        vm.updateItem(item.localId) { it.copy(lineTotal = "25,90", quantity = "1,0") }
        val sent = slot<ReceiptConfirmRequest>()
        coEvery { repository.confirmReceipt("r", capture(sent)) } returns receipt.copy(status = "CONFIRMED")
        vm.confirmReceipt(); advanceUntilIdle()
        assertTrue(vm.uiState.value.isConfirmed)
        assertEquals(BigDecimal("25.90"), sent.captured.total)
        assertEquals("2026-08-10T22:00:00Z", sent.captured.purchase_date)
    }

    @Test fun invalidQuantityIsNotSilentlyReplacedWithOne() = runTest {
        val vm = ReceiptReviewViewModel(SavedStateHandle(mapOf("receiptId" to "r")), repository)
        advanceUntilIdle()
        vm.updateItem(vm.uiState.value.items.single().localId) { it.copy(quantity = "oops") }
        vm.confirmReceipt(); advanceUntilIdle()
        assertNotNull(vm.uiState.value.error)
        coVerify(exactly = 0) { repository.confirmReceipt(any(), any()) }
    }

    @Test fun deleteReturnsToListAfterServerConfirmsDeletion() = runTest {
        val vm = ReceiptReviewViewModel(SavedStateHandle(mapOf("receiptId" to "r")), repository)
        advanceUntilIdle()
        coEvery { repository.deleteReceipt("r") } just Runs
        vm.deleteReceipt(); advanceUntilIdle()
        assertTrue(vm.uiState.value.isDeleted)
    }
}
