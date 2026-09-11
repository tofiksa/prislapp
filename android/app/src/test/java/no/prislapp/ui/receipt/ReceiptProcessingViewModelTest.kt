package no.prislapp.ui.receipt

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelStore
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.repository.ReceiptRepository
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class ReceiptProcessingViewModelTest {
    @Test
    fun pollGetFailureThenRetryDoesNotCallRetryReceipt() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val repository = mockk<ReceiptRepository>()
        val processing = PendingReceiptEntity(
            id = 1,
            imagePath = "/a.jpg",
            userId = "u",
            status = "processing",
            serverReceiptId = "srv-1",
        )
        coEvery { repository.getPendingReceipt(1) } returns processing
        coEvery { repository.getReceiptDetail("srv-1") } throws IOException("poll failed")
        coEvery { repository.retryReceipt(1) } returns Unit

        val store = ViewModelStore()
        try {
            val vm = ReceiptProcessingViewModel(
                SavedStateHandle(mapOf("localId" to 1L)),
                repository,
            )
            store.put("vm", vm)
            runCurrent()

            assertEquals("poll failed", vm.uiState.value.error)
            assertEquals("processing", vm.uiState.value.status)
            assertEquals("srv-1", vm.uiState.value.serverReceiptId)

            vm.retry()
            runCurrent()

            coVerify(exactly = 0) { repository.retryReceipt(any()) }
            coVerify(atLeast = 2) { repository.getReceiptDetail("srv-1") }
            assertEquals("processing", vm.uiState.value.status)
            assertEquals(true, vm.uiState.value.isPolling)
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }

    @Test
    fun needsActionRetryCallsRetryReceipt() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val repository = mockk<ReceiptRepository>()
        val needsAction = PendingReceiptEntity(
            id = 1,
            imagePath = "/a.jpg",
            userId = "u",
            status = "needs_action",
            serverReceiptId = "srv-1",
        )
        coEvery { repository.getPendingReceipt(1) } returns needsAction
        coEvery { repository.retryReceipt(1) } returns Unit

        val store = ViewModelStore()
        try {
            val vm = ReceiptProcessingViewModel(
                SavedStateHandle(mapOf("localId" to 1L)),
                repository,
            )
            store.put("vm", vm)
            runCurrent()

            vm.retry()
            runCurrent()

            coVerify(exactly = 1) { repository.retryReceipt(1) }
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }

    @Test
    fun queuedOfflineRetryCallsRetryReceiptWithoutOcrPoll() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val repository = mockk<ReceiptRepository>()
        val queued = PendingReceiptEntity(
            id = 1,
            imagePath = "/a.jpg",
            userId = "u",
            status = "queued_offline",
            serverReceiptId = null,
        )
        coEvery { repository.getPendingReceipt(1) } returns queued
        coEvery { repository.retryReceipt(1) } returns Unit

        val store = ViewModelStore()
        try {
            val vm = ReceiptProcessingViewModel(
                SavedStateHandle(mapOf("localId" to 1L)),
                repository,
            )
            store.put("vm", vm)
            runCurrent()

            vm.retry()
            runCurrent()

            coVerify(exactly = 1) { repository.retryReceipt(1) }
            coVerify(exactly = 0) { repository.getReceiptDetail(any()) }
        } finally {
            store.clear()
            Dispatchers.resetMain()
        }
    }
}
