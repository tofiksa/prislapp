package no.prislapp.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.ui.components.EmptyState
import no.prislapp.ui.components.PrislappTopBar
import no.prislapp.ui.components.ReceiptRow
import no.prislapp.ui.components.formatReceiptSubtitle
import no.prislapp.ui.receipt.receiptStatusLabel

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
    var accountMenuExpanded by remember { mutableStateOf(false) }
    LifecycleResumeEffect(Unit) {
        viewModel.refreshServerReceipts()
        onPauseOrDispose { }
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.home_title),
                actions = {
                    IconButton(onClick = { accountMenuExpanded = true }) {
                        Icon(
                            imageVector = Icons.Default.MoreVert,
                            contentDescription = stringResource(R.string.account_menu),
                        )
                    }
                    DropdownMenu(
                        expanded = accountMenuExpanded,
                        onDismissRequest = { accountMenuExpanded = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text(stringResource(R.string.logout)) },
                            onClick = {
                                accountMenuExpanded = false
                                onLogout()
                            },
                        )
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = onCaptureReceipt) {
                Icon(
                    imageVector = Icons.Default.PhotoCamera,
                    contentDescription = stringResource(R.string.capture_receipt),
                )
            }
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            item {
                Column {
                    TextButton(onClick = onOpenHistory) {
                        Text(stringResource(R.string.history_title))
                    }
                    TextButton(onClick = onOpenProductSearch) {
                        Text(stringResource(R.string.product_search_title))
                    }
                    if (uiState.isLoading) {
                        CircularProgressIndicator(modifier = Modifier.padding(top = 16.dp))
                    }
                }
            }

            if (!uiState.isLoading &&
                uiState.pendingReceipts.isEmpty() &&
                uiState.serverReceipts.isEmpty()
            ) {
                item {
                    EmptyState(
                        title = stringResource(R.string.home_empty_title),
                        body = stringResource(R.string.home_empty_body),
                    )
                }
            }

            if (uiState.pendingReceipts.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.upload_queue),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 24.dp),
                    )
                }
                items(uiState.pendingReceipts, key = { it.id }) { pending ->
                    ReceiptRow(
                        title = stringResource(R.string.queued_receipt),
                        subtitle = "",
                        statusLabel = receiptStatusLabel(pending.status),
                        onClick = {
                            if (pending.serverReceiptId != null &&
                                pending.status == PendingReceiptEntity.STATUS_READY_FOR_REVIEW
                            ) {
                                onOpenReceipt(pending.serverReceiptId)
                            } else {
                                onOpenPending(pending.id)
                            }
                        },
                    )
                }
            }

            if (uiState.serverReceipts.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.recent_receipts),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 24.dp),
                    )
                }
                items(uiState.serverReceipts, key = { it.id }) { receipt ->
                    ReceiptRow(
                        title = receipt.store?.name ?: stringResource(R.string.unknown_store),
                        subtitle = formatReceiptSubtitle(receipt.purchase_date, receipt.total),
                        statusLabel = receiptStatusLabel(receipt.status),
                        onClick = { onOpenReceipt(receipt.id) },
                    )
                }
            }

            uiState.error?.let { error ->
                item {
                    Text(
                        text = error,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
        }
    }
}
