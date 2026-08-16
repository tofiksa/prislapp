package no.prislapp.ui.receipt

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
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
    onConfirmed: () -> Unit,
    onBack: () -> Unit,
    viewModel: ReceiptReviewViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(uiState.isConfirmed) {
        if (uiState.isConfirmed) {
            onConfirmed()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.review_title)) })
        },
    ) { padding ->
        when {
            uiState.isLoading -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item {
                        OutlinedTextField(
                            value = uiState.storeName,
                            onValueChange = viewModel::updateStoreName,
                            label = { Text(stringResource(R.string.store_name)) },
                            modifier = Modifier.fillMaxWidth(),
                            readOnly = uiState.isReadOnly,
                            singleLine = true,
                        )
                    }
                    item {
                        OutlinedTextField(
                            value = uiState.total,
                            onValueChange = viewModel::updateTotal,
                            label = { Text(stringResource(R.string.receipt_total_label)) },
                            modifier = Modifier.fillMaxWidth(),
                            readOnly = uiState.isReadOnly,
                            singleLine = true,
                        )
                    }
                    item {
                        Text(
                            text = stringResource(R.string.receipt_items),
                            style = MaterialTheme.typography.titleMedium,
                        )
                    }
                    items(uiState.items, key = { it.localId }) { item ->
                        ReceiptItemEditor(
                            item = item,
                            readOnly = uiState.isReadOnly,
                            onNameChange = { value ->
                                viewModel.updateItem(item.localId) { it.copy(name = value) }
                            },
                            onQuantityChange = { value ->
                                viewModel.updateItem(item.localId) { it.copy(quantity = value) }
                            },
                            onUnitPriceChange = { value ->
                                viewModel.updateItem(item.localId) { it.copy(unitPrice = value) }
                            },
                            onLineTotalChange = { value ->
                                viewModel.updateItem(item.localId) { it.copy(lineTotal = value) }
                            },
                            onRemove = { viewModel.removeItem(item.localId) },
                        )
                    }
                    if (!uiState.isReadOnly) {
                        item {
                            OutlinedButton(onClick = viewModel::addItem) {
                                Text(stringResource(R.string.add_item))
                            }
                        }
                        item {
                            Button(
                                onClick = viewModel::confirmReceipt,
                                enabled = !uiState.isSaving,
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Text(
                                    if (uiState.isSaving) {
                                        stringResource(R.string.confirm_receipt) + "…"
                                    } else {
                                        stringResource(R.string.confirm_receipt)
                                    },
                                )
                            }
                        }
                    }
                    uiState.error?.let { error ->
                        item {
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReceiptItemEditor(
    item: EditableReceiptItem,
    readOnly: Boolean,
    onNameChange: (String) -> Unit,
    onQuantityChange: (String) -> Unit,
    onUnitPriceChange: (String) -> Unit,
    onLineTotalChange: (String) -> Unit,
    onRemove: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = item.name,
            onValueChange = onNameChange,
            label = { Text(stringResource(R.string.item_name)) },
            modifier = Modifier.fillMaxWidth(),
            readOnly = readOnly,
            singleLine = true,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = item.quantity,
                onValueChange = onQuantityChange,
                label = { Text(stringResource(R.string.item_quantity)) },
                modifier = Modifier.weight(1f),
                readOnly = readOnly,
                singleLine = true,
            )
            OutlinedTextField(
                value = item.unitPrice,
                onValueChange = onUnitPriceChange,
                label = { Text(stringResource(R.string.item_unit_price)) },
                modifier = Modifier.weight(1f),
                readOnly = readOnly,
                singleLine = true,
            )
            OutlinedTextField(
                value = item.lineTotal,
                onValueChange = onLineTotalChange,
                label = { Text(stringResource(R.string.item_line_total)) },
                modifier = Modifier.weight(1f),
                readOnly = readOnly,
                singleLine = true,
            )
        }
        if (!readOnly) {
            OutlinedButton(onClick = onRemove) {
                Text(stringResource(R.string.remove_item))
            }
        }
    }
}
