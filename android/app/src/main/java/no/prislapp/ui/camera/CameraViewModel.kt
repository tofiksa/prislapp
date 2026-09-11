package no.prislapp.ui.camera

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import no.prislapp.data.receipt.ReceiptImageFormat
import no.prislapp.data.receipt.ReceiptImageSniffResult
import no.prislapp.data.receipt.rotateReceiptImageIfNeeded
import no.prislapp.data.repository.ReceiptRepository
import java.io.File
import javax.inject.Inject

data class CameraUiState(
    val isSaving: Boolean = false,
    val savedLocalId: Long? = null,
    val error: String? = null,
    val errorResId: Int? = null,
    val previewFile: File? = null,
    val rotationDegrees: Int = 0,
)

@HiltViewModel
class CameraViewModel(
    private val receiptRepository: ReceiptRepository,
    private val ioDispatcher: CoroutineDispatcher,
) : ViewModel() {
    @Inject
    constructor(receiptRepository: ReceiptRepository) : this(receiptRepository, Dispatchers.IO)

    private val _uiState = MutableStateFlow(CameraUiState())
    val uiState: StateFlow<CameraUiState> = _uiState.asStateFlow()

    fun createOutputFile(): File = receiptRepository.createReceiptImageFile()

    fun onPhotoCaptured(imageFile: File) {
        viewModelScope.launch {
            showPreviewOrReject(imageFile)
        }
    }

    fun onGalleryImageSelected(sourceUri: Uri) {
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null, errorResId = null) }
            try {
                val file = withContext(ioDispatcher) { receiptRepository.copyReceiptImageFromUri(sourceUri) }
                showPreviewOrReject(file)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                onCaptureError(e.message ?: "Kunne ikke lese bildet")
            }
        }
    }

    fun acceptPreview() {
        val previewFile = _uiState.value.previewFile ?: return
        val rotationDegrees = _uiState.value.rotationDegrees
        viewModelScope.launch {
            _uiState.update { it.copy(isSaving = true, error = null, errorResId = null) }
            try {
                val queued = withContext(ioDispatcher) {
                    rotateReceiptImageIfNeeded(previewFile, rotationDegrees)
                }
                val localId = receiptRepository.queueReceiptCapture(queued)
                _uiState.update {
                    it.copy(isSaving = false, savedLocalId = localId, previewFile = null, rotationDegrees = 0)
                }
            } catch (e: CancellationException) {
                throw e
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

    fun retake() {
        val previewFile = _uiState.value.previewFile
        _uiState.update {
            it.copy(previewFile = null, rotationDegrees = 0, isSaving = false, error = null, errorResId = null)
        }
        if (previewFile != null) {
            viewModelScope.launch(ioDispatcher) { previewFile.delete() }
        }
    }

    fun rotatePreview() {
        if (_uiState.value.previewFile == null) return
        _uiState.update { it.copy(rotationDegrees = (it.rotationDegrees + 90) % 360) }
    }

    fun onCaptureError(message: String) {
        _uiState.update { it.copy(isSaving = false, error = message, errorResId = null) }
    }

    private suspend fun showPreviewOrReject(imageFile: File) {
        val sniff = withContext(ioDispatcher) { ReceiptImageFormat.sniffReceiptImage(imageFile) }
        when (sniff) {
            is ReceiptImageSniffResult.Accepted -> _uiState.update {
                it.copy(
                    isSaving = false,
                    previewFile = imageFile,
                    rotationDegrees = 0,
                    error = null,
                    errorResId = null,
                )
            }
            is ReceiptImageSniffResult.Rejected -> {
                withContext(ioDispatcher) { imageFile.delete() }
                _uiState.update {
                    it.copy(
                        isSaving = false,
                        previewFile = null,
                        rotationDegrees = 0,
                        error = null,
                        errorResId = sniff.messageResId,
                    )
                }
            }
        }
    }
}
