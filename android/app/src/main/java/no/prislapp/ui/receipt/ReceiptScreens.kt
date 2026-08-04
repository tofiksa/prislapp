package no.prislapp.ui.receipt

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import no.prislapp.data.local.entity.PendingReceiptEntity

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptProcessingScreen(
    onReadyForReview: (receiptId: String) -> Unit,
    onBack: () -> Unit,
    viewModel: ReceiptProcessingViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(uiState.status, uiState.serverReceiptId) {
        val serverReceiptId = uiState.serverReceiptId
        if (uiState.status == PendingReceiptEntity.STATUS_READY_FOR_REVIEW &&
            serverReceiptId != null
        ) {
            onReadyForReview(serverReceiptId)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.processing_title)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            if (uiState.isPolling) {
                CircularProgressIndicator()
            }
            Text(
                text = stringResource(R.string.processing_status, uiState.status),
                modifier = Modifier.padding(top = 16.dp),
            )
            uiState.error?.let { error ->
                Text(
                    text = error,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptReviewScreen(
    onBack: () -> Unit,
    viewModel: ReceiptReviewViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.review_title)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            when {
                uiState.isLoading -> CircularProgressIndicator()
                uiState.error != null -> Text(text = uiState.error!!)
                uiState.receipt != null -> {
                    val receipt = uiState.receipt!!
                    Text(
                        text = receipt.store?.name ?: stringResource(R.string.unknown_store),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    receipt.total?.let { total ->
                        Text(
                            text = stringResource(R.string.receipt_total, total.toPlainString()),
                            modifier = Modifier.padding(top = 8.dp),
                        )
                    }
                    Text(
                        text = stringResource(R.string.review_placeholder),
                        modifier = Modifier.padding(top = 16.dp),
                    )
                    LazyColumn(modifier = Modifier.padding(top = 8.dp)) {
                        items(receipt.items) { item ->
                            Text(
                                text = "${item.raw_product_name} – ${item.line_total.toPlainString()} kr",
                                modifier = Modifier.padding(vertical = 4.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}
