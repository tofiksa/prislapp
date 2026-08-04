package no.prislapp.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import no.prislapp.data.repository.ReceiptRepository
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(HomeUiState())
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        observePending()
        refreshServerReceipts()
    }

    private fun observePending() {
        viewModelScope.launch {
            receiptRepository.observePendingReceipts().collect { pending ->
                _uiState.update { it.copy(pendingReceipts = pending) }
            }
        }
    }

    fun refreshServerReceipts() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val response = receiptRepository.listReceipts()
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        serverReceipts = response.items,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, error = e.message ?: "Kunne ikke hente kvitteringer")
                }
            }
        }
    }
}
