package no.prislapp.ui.product

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import no.prislapp.ui.components.PrislappTopBar
import no.prislapp.ui.components.ReceiptRow
import no.prislapp.ui.components.formatReceiptSubtitle
import java.math.BigDecimal

@Composable
fun ProductSearchScreen(
    onOpenProduct: (productId: String) -> Unit,
    onBack: (() -> Unit)? = null,
    viewModel: ProductSearchViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.product_search_title),
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
            OutlinedTextField(
                value = uiState.query,
                onValueChange = viewModel::updateQuery,
                label = { Text(stringResource(R.string.search_products)) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )

            if (uiState.isSearching) {
                CircularProgressIndicator(modifier = Modifier.padding(top = 16.dp))
            }
            if (uiState.hasSearched && uiState.results.isEmpty()) {
                Text(stringResource(R.string.no_products))
            }

            LazyColumn(modifier = Modifier.padding(top = 16.dp)) {
                items(uiState.results, key = { it.id }) { product ->
                    ReceiptRow(
                        title = product.canonical_name,
                        subtitle = "",
                        statusLabel = null,
                        onClick = { onOpenProduct(product.id) },
                    )
                }
            }

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

@Composable
fun ProductPricesScreen(
    onBack: () -> Unit,
    viewModel: ProductPricesViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.cheapest_for_me_title),
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
            when {
                uiState.isLoading -> CircularProgressIndicator()
                uiState.prices != null -> {
                    val prices = uiState.prices!!
                    Text(
                        text = prices.product.canonical_name,
                        style = MaterialTheme.typography.titleLarge,
                    )
                    val cheapest = prices.cheapest
                    if (cheapest != null) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 16.dp),
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(
                                    text = stringResource(
                                        R.string.cheapest_price,
                                        cheapest.store.name,
                                        cheapest.price.toPlainString().replace('.', ','),
                                    ),
                                    style = MaterialTheme.typography.headlineSmall,
                                )
                                Text(
                                    text = formatReceiptSubtitle(cheapest.observed_at, null),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(top = 8.dp),
                                )
                            }
                        }
                        Text(
                            text = stringResource(R.string.price_per_unit),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(top = 12.dp),
                        )
                        LazyColumn(
                            modifier = Modifier
                                .weight(1f)
                                .padding(top = 16.dp),
                        ) {
                            item {
                                Text(
                                    text = stringResource(R.string.latest_store_prices),
                                    style = MaterialTheme.typography.titleMedium,
                                )
                            }
                            items(prices.latest_by_store) { observation ->
                                Text(
                                    text = formatPriceObservationLine(
                                        storeName = observation.store.name,
                                        price = observation.price,
                                        observedAt = observation.observed_at,
                                    ),
                                    style = MaterialTheme.typography.bodyLarge,
                                    modifier = Modifier.padding(vertical = 4.dp),
                                )
                            }
                            item {
                                Text(
                                    text = stringResource(R.string.all_observations),
                                    style = MaterialTheme.typography.titleSmall,
                                    modifier = Modifier.padding(top = 16.dp),
                                )
                            }
                            items(prices.observations) { observation ->
                                Text(
                                    text = formatPriceObservationLine(
                                        storeName = observation.store.name,
                                        price = observation.price,
                                        observedAt = observation.observed_at,
                                    ),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(vertical = 4.dp),
                                )
                            }
                        }
                    } else {
                        Text(
                            text = stringResource(R.string.no_price_observations),
                            modifier = Modifier.padding(top = 16.dp),
                        )
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
        }
    }
}

private fun formatPriceObservationLine(
    storeName: String,
    price: BigDecimal,
    observedAt: String,
): String {
    val priceText = formatReceiptSubtitle(null, price)
    val dateText = formatReceiptSubtitle(observedAt, null)
    return "$storeName · $priceText · $dateText"
}
