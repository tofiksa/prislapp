package no.prislapp.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import no.prislapp.ui.components.EmptyState
import no.prislapp.ui.components.PrislappTopBar
import no.prislapp.ui.components.ReceiptRow
import no.prislapp.ui.components.formatReceiptSubtitle
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

private enum class ActiveDatePicker {
    FROM,
    TO,
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun HistoryScreen(
    onOpenReceipt: (receiptId: String) -> Unit,
    onBack: (() -> Unit)? = null,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    var activeDatePicker by remember { mutableStateOf<ActiveDatePicker?>(null) }

    val openPicker = activeDatePicker
    if (openPicker != null) {
        val initialDateMillis = when (openPicker) {
            ActiveDatePicker.FROM -> uiState.fromDate?.toEpochMillis()
            ActiveDatePicker.TO -> uiState.toDate?.toEpochMillis()
        }
        val datePickerState = rememberDatePickerState(initialSelectedDateMillis = initialDateMillis)

        DatePickerDialog(
            onDismissRequest = { activeDatePicker = null },
            confirmButton = {
                TextButton(
                    onClick = {
                        val selectedDate = datePickerState.selectedDateMillis?.toLocalDate()
                        when (openPicker) {
                            ActiveDatePicker.FROM -> viewModel.setFromDate(selectedDate)
                            ActiveDatePicker.TO -> viewModel.setToDate(selectedDate)
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
                title = stringResource(R.string.history_title),
                onBack = onBack,
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                Text(
                    text = stringResource(R.string.filter_by_date),
                    style = MaterialTheme.typography.titleSmall,
                )
            }
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    TextButton(
                        onClick = { activeDatePicker = ActiveDatePicker.FROM },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(
                            uiState.fromDateLabel ?: stringResource(R.string.from_date),
                        )
                    }
                    TextButton(
                        onClick = { activeDatePicker = ActiveDatePicker.TO },
                        modifier = Modifier.weight(1f),
                    ) {
                        Text(
                            uiState.toDateLabel ?: stringResource(R.string.to_date),
                        )
                    }
                }
            }
            if (uiState.hasDateFilter) {
                item {
                    TextButton(onClick = viewModel::clearDateFilter) {
                        Text(stringResource(R.string.clear_date_filter))
                    }
                }
            }

            if (uiState.stores.isNotEmpty()) {
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
                            selected = uiState.selectedStoreId == null,
                            onClick = { viewModel.selectStore(null) },
                            label = { Text(stringResource(R.string.all_stores)) },
                        )
                        uiState.stores.forEach { store ->
                            FilterChip(
                                selected = uiState.selectedStoreId == store.id,
                                onClick = { viewModel.selectStore(store.id) },
                                label = { Text(store.name) },
                            )
                        }
                    }
                }
            }

            if (uiState.isLoading) {
                item { CircularProgressIndicator() }
            }
            if (!uiState.isLoading && uiState.receipts.isEmpty()) {
                item {
                    EmptyState(
                        title = stringResource(R.string.history_empty_title),
                        body = stringResource(R.string.history_empty_body),
                    )
                }
            }

            items(uiState.receipts, key = { it.id }) { receipt ->
                ReceiptRow(
                    title = receipt.store?.name ?: stringResource(R.string.unknown_store),
                    subtitle = formatReceiptSubtitle(receipt.purchase_date, receipt.total),
                    statusLabel = null,
                    onClick = { onOpenReceipt(receipt.id) },
                )
            }

            uiState.error?.let { error ->
                item {
                    Text(
                        text = error,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                item { TextButton(onClick = viewModel::reload) { Text(stringResource(R.string.retry)) } }
            }
            if (uiState.hasMore) {
                item { TextButton(onClick = viewModel::loadMore, enabled = !uiState.isLoading) {
                    Text(stringResource(R.string.load_more))
                } }
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
