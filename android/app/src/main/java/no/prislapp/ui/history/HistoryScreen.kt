package no.prislapp.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    onOpenReceipt: (receiptId: String) -> Unit,
    onBack: () -> Unit,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.history_title)) })
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (uiState.stores.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.filter_by_store),
                        style = MaterialTheme.typography.titleSmall,
                    )
                }
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
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

            items(uiState.receipts, key = { it.id }) { receipt ->
                OutlinedButton(
                    onClick = { onOpenReceipt(receipt.id) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    val storeName = receipt.store?.name ?: stringResource(R.string.unknown_store)
                    val total = receipt.total?.toPlainString() ?: "?"
                    Text("$storeName – $total kr")
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
