package no.prislapp.ui.camera

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import no.prislapp.data.repository.ReceiptRepository
import java.io.File
import javax.inject.Inject

data class CameraUiState(
    val isSaving: Boolean = false,
    val savedLocalId: Long? = null,
    val error: String? = null,
)

@HiltViewModel
class CameraViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(CameraUiState())
    val uiState: StateFlow<CameraUiState> = _uiState.asStateFlow()

    fun createOutputFile(): File = receiptRepository.createReceiptImageFile()

    fun onPhotoCaptured(imageFile: File) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null) }
            try {
                val localId = receiptRepository.queueReceiptCapture(imageFile)
                _uiState.update { it.copy(isSaving = false, savedLocalId = localId) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        error = e.message ?: "Kunne ikke lagre kvittering",
                    )
                }
            }
        }
    }
}
