package no.prislapp.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
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
fun HomeScreen(
    onCaptureReceipt: () -> Unit,
    onOpenReceipt: (receiptId: String) -> Unit,
    onOpenPending: (localId: Long) -> Unit,
    onOpenHistory: () -> Unit,
    onOpenProductSearch: () -> Unit,
    onLogout: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.home_title)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            Text(text = stringResource(R.string.welcome))

            OutlinedButton(
                onClick = onCaptureReceipt,
                modifier = Modifier.padding(top = 16.dp),
            ) {
                Text(stringResource(R.string.capture_receipt))
            }

            OutlinedButton(
                onClick = onOpenHistory,
                modifier = Modifier.padding(top = 8.dp),
            ) {
                Text(stringResource(R.string.history_title))
            }

            OutlinedButton(
                onClick = onOpenProductSearch,
                modifier = Modifier.padding(top = 8.dp),
            ) {
                Text(stringResource(R.string.product_search_title))
            }

            if (uiState.isLoading) {
                CircularProgressIndicator(modifier = Modifier.padding(top = 16.dp))
            }

            if (uiState.pendingReceipts.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.upload_queue),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 24.dp),
                )
                LazyColumn {
                    items(uiState.pendingReceipts, key = { it.id }) { pending ->
                        OutlinedButton(
                            onClick = {
                                if (pending.serverReceiptId != null &&
                                    pending.status == PendingReceiptEntity.STATUS_READY_FOR_REVIEW
                                ) {
                                    onOpenReceipt(pending.serverReceiptId)
                                } else {
                                    onOpenPending(pending.id)
                                }
                            },
                            modifier = Modifier.padding(top = 8.dp),
                        ) {
                            Text("${pending.status} (#${pending.id})")
                        }
                    }
                }
            }

            if (uiState.serverReceipts.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.recent_receipts),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 24.dp),
                )
                LazyColumn {
                    items(uiState.serverReceipts, key = { it.id }) { receipt ->
                        OutlinedButton(
                            onClick = { onOpenReceipt(receipt.id) },
                            modifier = Modifier.padding(top = 8.dp),
                        ) {
                            Text("${receipt.store?.name ?: "?"} – ${receipt.status}")
                        }
                    }
                }
            }

            uiState.error?.let { error ->
                Text(
                    text = error,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            Button(
                onClick = onLogout,
                modifier = Modifier.padding(top = 24.dp),
            ) {
                Text(stringResource(R.string.logout))
            }
        }
    }
}
