package no.prislapp.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import androidx.compose.material3.AlertDialog
import no.prislapp.data.local.entity.canRetry
import no.prislapp.data.local.entity.canonicalStatus
import no.prislapp.data.local.entity.ReceiptQueueStatus
import no.prislapp.ui.components.EmptyState
import no.prislapp.ui.components.PrislappTopBar
import no.prislapp.ui.components.ReceiptRow
import no.prislapp.ui.components.formatCaptureTime
import no.prislapp.ui.components.formatReceiptSubtitle
import no.prislapp.ui.history.HistoryViewModel
import no.prislapp.ui.receipt.receiptStatusLabel
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

private enum class ActiveDatePicker {
    FROM,
    TO,
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ReceiptsScreen(
    onCaptureReceipt: () -> Unit,
    onOpenReceipt: (receiptId: String) -> Unit,
    onOpenPending: (localId: Long) -> Unit,
    onCopiedToShoppingList: () -> Unit = {},
    onLogout: () -> Unit,
    homeViewModel: HomeViewModel = hiltViewModel(),
    historyViewModel: HistoryViewModel = hiltViewModel(),
) {
    val homeState by homeViewModel.uiState.collectAsStateWithLifecycle()
    val historyState by historyViewModel.uiState.collectAsStateWithLifecycle()
    var accountMenuExpanded by remember { mutableStateOf(false) }
    var activeDatePicker by remember { mutableStateOf<ActiveDatePicker?>(null) }
    var pendingRemoveId by remember { mutableStateOf<Long?>(null) }

    LifecycleResumeEffect(Unit) {
        homeViewModel.refreshServerReceipts()
        historyViewModel.reload()
        onPauseOrDispose { }
    }

    pendingRemoveId?.let { localId ->
        AlertDialog(
            onDismissRequest = { pendingRemoveId = null },
            title = { Text(stringResource(R.string.remove_local_receipt_title)) },
            text = { Text(stringResource(R.string.remove_local_receipt_message)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        homeViewModel.removeLocalReceipt(localId)
                        pendingRemoveId = null
                    },
                    modifier = Modifier.height(48.dp),
                ) {
                    Text(stringResource(R.string.remove_local_receipt))
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { pendingRemoveId = null },
                    modifier = Modifier.height(48.dp),
                ) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }

    val openPicker = activeDatePicker
    if (openPicker != null) {
        val initialDateMillis = when (openPicker) {
            ActiveDatePicker.FROM -> historyState.fromDate?.toEpochMillis()
            ActiveDatePicker.TO -> historyState.toDate?.toEpochMillis()
        }
        val datePickerState = rememberDatePickerState(initialSelectedDateMillis = initialDateMillis)

        DatePickerDialog(
            onDismissRequest = { activeDatePicker = null },
            confirmButton = {
                TextButton(
                    onClick = {
                        val selectedDate = datePickerState.selectedDateMillis?.toLocalDate()
                        when (openPicker) {
                            ActiveDatePicker.FROM -> historyViewModel.setFromDate(selectedDate)
                            ActiveDatePicker.TO -> historyViewModel.setToDate(selectedDate)
                        }
                        activeDatePicker = null
                    },
                ) {
                    Text(stringResource(R.string.select_date_confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = { activeDatePicker = null }) {
                    Text(stringResource(R.string.select_date_cancel))
                }
            },
        ) {
            DatePicker(state = datePickerState)
        }
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.receipts_title),
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
            contentPadding = PaddingValues(bottom = 88.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (homeState.showUnuploadedRetentionBanner) {
                item {
                    Text(
                        text = stringResource(R.string.unuploaded_retention_banner),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            if (homeState.pendingReceipts.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.upload_queue),
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
                items(homeState.pendingReceipts, key = { "pending-${it.id}" }) { pending ->
                    val thumbnail = pending.imagePath.takeIf { File(it).exists() }
                    val status = pending.canonicalStatus()
                    ReceiptRow(
                        title = stringResource(R.string.queued_receipt),
                        subtitle = formatCaptureTime(pending.createdAt),
                        statusLabel = receiptStatusLabel(pending.status),
                        thumbnailPath = thumbnail,
                        onClick = {
                            if (pending.serverReceiptId != null &&
                                status == ReceiptQueueStatus.READY_FOR_REVIEW
                            ) {
                                onOpenReceipt(pending.serverReceiptId)
                            } else {
                                onOpenPending(pending.id)
                            }
                        },
                        actionLabel = if (pending.canRetry()) {
                            stringResource(R.string.retry)
                        } else {
                            null
                        },
                        onAction = if (pending.canRetry()) {
                            { homeViewModel.retryQueueItem(pending.id) }
                        } else {
                            null
                        },
                        secondaryActionLabel = stringResource(R.string.remove_local_receipt),
                        onSecondaryAction = { pendingRemoveId = pending.id },
                    )
                }
            }

            item {
                Text(
                    text = stringResource(R.string.filter_by_date),
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    TextButton(
                        onClick = { activeDatePicker = ActiveDatePicker.FROM },
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp),
                    ) {
                        Text(
                            historyState.fromDateLabel ?: stringResource(R.string.from_date),
                        )
                    }
                    TextButton(
                        onClick = { activeDatePicker = ActiveDatePicker.TO },
                        modifier = Modifier
                            .weight(1f)
                            .height(48.dp),
                    ) {
                        Text(
                            historyState.toDateLabel ?: stringResource(R.string.to_date),
                        )
                    }
                }
            }
            if (historyState.hasDateFilter) {
                item {
                    TextButton(onClick = historyViewModel::clearDateFilter) {
                        Text(stringResource(R.string.clear_date_filter))
                    }
                }
            }

            if (historyState.stores.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.filter_by_store),
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
                item {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        FilterChip(
                            selected = historyState.selectedStoreId == null,
                            onClick = { historyViewModel.selectStore(null) },
                            label = { Text(stringResource(R.string.all_stores)) },
                        )
                        historyState.stores.forEach { store ->
                            FilterChip(
                                selected = historyState.selectedStoreId == store.id,
                                onClick = { historyViewModel.selectStore(store.id) },
                                label = { Text(store.name) },
                            )
                        }
                    }
                }
            }

            if (homeState.isLoading || historyState.isLoading) {
                item { CircularProgressIndicator() }
            }

            val showEmpty = !homeState.isLoading &&
                !historyState.isLoading &&
                homeState.pendingReceipts.isEmpty() &&
                historyState.receipts.isEmpty()
            if (showEmpty) {
                item {
                    EmptyState(
                        title = stringResource(R.string.home_empty_title),
                        body = stringResource(R.string.home_empty_body),
                    )
                }
            }

            items(historyState.receipts, key = { it.id }) { receipt ->
                ReceiptRow(
                    title = receipt.store?.name ?: stringResource(R.string.unknown_store),
                    subtitle = formatReceiptSubtitle(receipt.purchase_date, receipt.total),
                    statusLabel = receiptStatusLabel(receipt.status),
                    onClick = { onOpenReceipt(receipt.id) },
                    actionLabel = if (receipt.status == "CONFIRMED") {
                        stringResource(R.string.use_in_shopping_list)
                    } else {
                        null
                    },
                    onAction = if (receipt.status == "CONFIRMED") {
                        {
                            historyViewModel.useInShoppingList(receipt.id, onCopiedToShoppingList)
                        }
                    } else {
                        null
                    },
                )
            }

            homeState.error?.let { error ->
                item {
                    Text(
                        text = error,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            historyState.error?.let { error ->
                item {
                    Text(
                        text = error,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                item {
                    TextButton(onClick = historyViewModel::reload) {
                        Text(stringResource(R.string.retry))
                    }
                }
            }
            if (historyState.hasMore) {
                item {
                    TextButton(
                        onClick = historyViewModel::loadMore,
                        enabled = !historyState.isLoading,
                    ) {
                        Text(stringResource(R.string.load_more))
                    }
                }
            }
        }
    }
}

private fun LocalDate.toEpochMillis(): Long {
    return atStartOfDay(ZoneId.of("UTC")).toInstant().toEpochMilli()
}

private fun Long.toLocalDate(): LocalDate {
    return Instant.ofEpochMilli(this).atZone(ZoneId.of("UTC")).toLocalDate()
}
