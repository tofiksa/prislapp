package no.prislapp.ui.product

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TextButton
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductPricesScreen(
    onBack: () -> Unit,
    viewModel: ProductPricesViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.cheapest_for_me_title)) },
                navigationIcon = { TextButton(onClick = onBack) { Text(stringResource(R.string.back)) } })
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
                    prices.cheapest?.let { cheapest ->
                        Text(
                            text = stringResource(
                                R.string.cheapest_price,
                                cheapest.store.name,
                                cheapest.price.toPlainString(),
                            ),
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = 16.dp),
                        )
                    }
                    LazyColumn(modifier = Modifier.padding(top = 8.dp)) {
                        item { Text(stringResource(R.string.price_per_unit)) }
                        item { Text(stringResource(R.string.latest_store_prices), style = MaterialTheme.typography.titleSmall) }
                        items(prices.latest_by_store) { observation ->
                            Text("${observation.store.name}: ${observation.price.toPlainString()} kr (${observation.observed_at.take(10)})",
                                modifier = Modifier.padding(vertical = 4.dp))
                        }
                        item { Text(stringResource(R.string.all_observations), style = MaterialTheme.typography.titleSmall,
                            modifier = Modifier.padding(top = 16.dp)) }
                        items(prices.observations) { observation ->
                            Text(
                                text = "${observation.store.name}: ${observation.price.toPlainString()} kr (${observation.observed_at.take(10)})",
                                modifier = Modifier.padding(vertical = 4.dp),
                            )
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
        }
    }
}
