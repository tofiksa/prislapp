package no.prislapp.ui.camera

import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import no.prislapp.data.repository.ReceiptRepository
import org.junit.*
import org.junit.Assert.*

@OptIn(ExperimentalCoroutinesApi::class)
class CameraViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }
    @Test fun cameraFailureIsVisibleAndAllowsRetry() {
        val vm = CameraViewModel(mockk<ReceiptRepository>())
        vm.onCaptureError("Kamera utilgjengelig")
        assertEquals("Kamera utilgjengelig", vm.uiState.value.error)
        assertFalse(vm.uiState.value.isSaving)
    }
}
