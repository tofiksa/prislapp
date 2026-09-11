package no.prislapp.ui.receipt

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.SubcomposeAsyncImage
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import no.prislapp.R
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.ui.components.PrislappTopBar

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

    val canonical = no.prislapp.data.local.entity.ReceiptQueueStatus.canonical(
        uiState.status,
        uiState.serverReceiptId,
    )
    val bodyText = when (canonical) {
        no.prislapp.data.local.entity.ReceiptQueueStatus.QUEUED_OFFLINE,
        no.prislapp.data.local.entity.ReceiptQueueStatus.UPLOADING,
        -> stringResource(R.string.processing_body_upload)
        no.prislapp.data.local.entity.ReceiptQueueStatus.PROCESSING ->
            stringResource(R.string.processing_body_ocr)
        no.prislapp.data.local.entity.ReceiptQueueStatus.NEEDS_ACTION,
        no.prislapp.data.local.entity.ReceiptQueueStatus.FAILED_PERMANENT,
        -> stringResource(R.string.processing_body_failed)
        else -> receiptStatusLabel(uiState.status)
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.processing_title),
                onBack = onBack,
            )
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
                text = bodyText,
                modifier = Modifier.padding(top = 16.dp),
            )
            if (canonical == no.prislapp.data.local.entity.ReceiptQueueStatus.NEEDS_ACTION ||
                (canonical == no.prislapp.data.local.entity.ReceiptQueueStatus.QUEUED_OFFLINE) ||
                uiState.error != null
            ) {
                OutlinedButton(onClick = viewModel::retry) { Text(stringResource(R.string.retry)) }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiptReviewScreen(
    onConfirmed: (readyCount: Int) -> Unit,
    onBack: () -> Unit,
    viewModel: ReceiptReviewViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    var confirmDelete by remember { mutableStateOf(false) }
    var showDatePicker by remember { mutableStateOf(false) }
    var showOcr by remember { mutableStateOf(false) }

    if (confirmDelete) {
        AlertDialog(onDismissRequest = { confirmDelete = false },
            title = { Text(stringResource(R.string.delete_receipt)) },
            text = { Text(stringResource(R.string.delete_receipt_message)) },
            confirmButton = { TextButton(onClick = { confirmDelete = false; viewModel.deleteReceipt() }) {
                Text(stringResource(R.string.delete_receipt))
            } },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text(stringResource(R.string.cancel)) } })
    }
    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(
            initialSelectedDateMillis = uiState.purchaseDate.toLocalDateOrNull()?.toEpochMillis(),
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        datePickerState.selectedDateMillis?.toLocalDate()?.let { selected ->
                            viewModel.updatePurchaseDate(selected.format(purchaseDateFormatter))
                        }
                        showDatePicker = false
                    },
                ) {
                    Text(stringResource(R.string.select_date_confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) {
                    Text(stringResource(R.string.select_date_cancel))
                }
            },
        ) {
            DatePicker(state = datePickerState)
        }
    }
    LaunchedEffect(uiState.isDeleted) { if (uiState.isDeleted) onConfirmed(0) }
    LaunchedEffect(uiState.status) {
        while (uiState.status == "UPLOADED" || uiState.status == "PROCESSING") {
            kotlinx.coroutines.delay(3_000)
            viewModel.reload()
        }
    }

    LaunchedEffect(uiState.isConfirmed) {
        if (uiState.isConfirmed) {
            onConfirmed(uiState.items.size)
        }
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.review_title),
                onBack = onBack,
            )
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
                    item { ReceiptReviewImage(uiState.localImagePath, uiState.imageUrl) }
                    if (uiState.status == "FAILED") {
                        item { OutlinedButton(onClick = viewModel::retryProcessing) { Text(stringResource(R.string.retry)) } }
                    }
                    if (uiState.status == "PROCESSING" || uiState.status == "UPLOADED") {
                        item {
                            Text(
                                if (uiState.status == "PROCESSING") {
                                    stringResource(R.string.processing_body_ocr)
                                } else {
                                    stringResource(R.string.processing_body_upload)
                                },
                            )
                        }
                    }
                    item {
                        Box {
                            OutlinedTextField(
                                value = uiState.purchaseDate,
                                onValueChange = {},
                                label = { Text(stringResource(R.string.purchase_date)) },
                                modifier = Modifier.fillMaxWidth(),
                                readOnly = true,
                                singleLine = true,
                            )
                            if (!uiState.isReadOnly) {
                                val purchaseDateLabel = stringResource(R.string.purchase_date)
                                Box(
                                    modifier = Modifier
                                        .matchParentSize()
                                        .clickable { showDatePicker = true }
                                        .semantics { contentDescription = purchaseDateLabel },
                                )
                            }
                        }
                    }
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
                            TextButton(onClick = viewModel::addItem) {
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
                    if (uiState.rawOcrText.isNotBlank()) {
                        item {
                            TextButton(onClick = { showOcr = !showOcr }) {
                                Text(
                                    stringResource(
                                        if (showOcr) R.string.hide_ocr else R.string.show_ocr,
                                    ),
                                )
                            }
                        }
                        if (showOcr) {
                            item { Text(uiState.rawOcrText) }
                        }
                    }
                    item {
                        TextButton(
                            onClick = { confirmDelete = true },
                            enabled = !uiState.isSaving,
                        ) {
                            Text(
                                text = stringResource(R.string.delete_receipt),
                                color = MaterialTheme.colorScheme.error,
                            )
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
private fun ReceiptReviewImage(localImagePath: String?, imageUrl: String?) {
    val model = localImagePath?.let { java.io.File(it) } ?: imageUrl
    SubcomposeAsyncImage(
        model = model,
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = Modifier
            .height(180.dp)
            .fillMaxWidth(),
        error = { Text(stringResource(R.string.image_unavailable)) },
    )
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
    OutlinedCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
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
                TextButton(onClick = onRemove) {
                    Text(stringResource(R.string.remove_item))
                }
            }
        }
    }
}

private val purchaseDateFormatter: DateTimeFormatter = DateTimeFormatter.ofPattern("dd.MM.yyyy")

private fun LocalDate.toEpochMillis(): Long {
    return atStartOfDay(ZoneId.of("UTC")).toInstant().toEpochMilli()
}

private fun Long.toLocalDate(): LocalDate {
    return Instant.ofEpochMilli(this).atZone(ZoneId.of("UTC")).toLocalDate()
}

private fun String.toLocalDateOrNull(): LocalDate? {
    return runCatching { LocalDate.parse(this, purchaseDateFormatter) }.getOrNull()
}
