package no.prislapp.ui.shoppinglist

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import no.prislapp.R
import no.prislapp.ui.components.EmptyState
import no.prislapp.ui.components.PrislappTopBar

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShoppingListScreen(
    viewModel: ShoppingListViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val listSnackbarHostState = remember { SnackbarHostState() }
    val sheetSnackbarHostState = remember { SnackbarHostState() }
    val undoMessage = when (uiState.pendingUndo) {
        is ShoppingListUndo.RestoreQuantity -> stringResource(R.string.shopping_list_quantity_updated)
        is ShoppingListUndo.Undelete -> stringResource(R.string.shopping_list_item_removed)
        null -> null
    }
    val undoLabel = stringResource(R.string.shopping_list_undo)
    val pendingUndo = uiState.pendingUndo

    LaunchedEffect(pendingUndo, uiState.undoSnackbarOnSheet) {
        val message = undoMessage ?: return@LaunchedEffect
        val host = if (uiState.undoSnackbarOnSheet) {
            sheetSnackbarHostState
        } else {
            listSnackbarHostState
        }
        val other = if (uiState.undoSnackbarOnSheet) {
            listSnackbarHostState
        } else {
            sheetSnackbarHostState
        }
        other.currentSnackbarData?.dismiss()
        host.currentSnackbarData?.dismiss()
        val result = host.showSnackbar(
            message = message,
            actionLabel = undoLabel,
        )
        if (result == SnackbarResult.ActionPerformed) {
            viewModel.undo()
        } else if (viewModel.uiState.value.pendingUndo === pendingUndo) {
            viewModel.dismissUndo()
        }
    }

    Scaffold(
        topBar = {
            PrislappTopBar(title = stringResource(R.string.shopping_list_title))
        },
        snackbarHost = { SnackbarHost(listSnackbarHostState) },
        floatingActionButton = {
            FloatingActionButton(onClick = viewModel::openAddSheet) {
                Icon(
                    imageVector = Icons.Default.Add,
                    contentDescription = stringResource(R.string.shopping_list_add),
                )
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
        ) {
            if (uiState.showConflictBanner) {
                Text(
                    text = stringResource(R.string.shopping_list_conflict_banner),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 8.dp, bottom = 8.dp),
                )
            }
            if (uiState.items.isEmpty()) {
                EmptyState(
                    title = stringResource(R.string.shopping_list_empty_title),
                    body = stringResource(R.string.shopping_list_empty_body),
                    modifier = Modifier.padding(top = 32.dp),
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(bottom = 88.dp),
                ) {
                    items(uiState.items, key = { it.id }) { item ->
                        ShoppingListItemRow(
                            item = item,
                            onCheckedChange = { viewModel.setChecked(item.id, it) },
                            onIncrement = { viewModel.incrementQuantity(item.id) },
                            onDecrement = { viewModel.decrementQuantity(item.id) },
                            onDelete = { viewModel.deleteItem(item.id) },
                        )
                    }
                }
            }
        }
    }

    if (uiState.showAddSheet) {
        AddItemSheet(
            recentProducts = uiState.recentProducts,
            catalogOfflineEmpty = uiState.catalogOfflineEmpty,
            snackbarHostState = if (uiState.undoSnackbarOnSheet) sheetSnackbarHostState else null,
            onAddProduct = viewModel::addRecentProduct,
            onAddFreeText = viewModel::addFreeText,
            onDismiss = viewModel::dismissAddSheet,
        )
    }
}

@Composable
private fun ShoppingListItemRow(
    item: ShoppingListItemUi,
    onCheckedChange: (Boolean) -> Unit,
    onIncrement: () -> Unit,
    onDecrement: () -> Unit,
    onDelete: () -> Unit,
) {
    val checkedDescription = if (item.checked) {
        stringResource(R.string.shopping_list_checked)
    } else {
        stringResource(R.string.shopping_list_unchecked)
    }
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(
                checked = item.checked,
                onCheckedChange = onCheckedChange,
                modifier = Modifier
                    .size(48.dp)
                    .semantics { stateDescription = checkedDescription },
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.displayName,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (item.checked) {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    } else {
                        MaterialTheme.colorScheme.onSurface
                    },
                )
                val details = listOfNotNull(
                    item.packLabel,
                    item.quantityLabel,
                    if (item.noPriceHistory) {
                        stringResource(R.string.shopping_list_no_price_history)
                    } else {
                        null
                    },
                ).joinToString(" · ")
                if (details.isNotBlank()) {
                    Text(
                        text = details,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            IconButton(
                onClick = onDecrement,
                modifier = Modifier.size(48.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.Remove,
                    contentDescription = stringResource(R.string.shopping_list_decrease_quantity),
                )
            }
            IconButton(
                onClick = onIncrement,
                modifier = Modifier.size(48.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.Add,
                    contentDescription = stringResource(R.string.shopping_list_increase_quantity),
                )
            }
            IconButton(
                onClick = onDelete,
                modifier = Modifier.size(48.dp),
            ) {
                Icon(
                    imageVector = Icons.Default.Delete,
                    contentDescription = stringResource(R.string.shopping_list_remove),
                )
            }
        }
        HorizontalDivider()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddItemSheet(
    recentProducts: List<RecentProductUi>,
    catalogOfflineEmpty: Boolean,
    snackbarHostState: SnackbarHostState?,
    onAddProduct: (String) -> Unit,
    onAddFreeText: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var selectedTab by remember { mutableIntStateOf(0) }
    var freeText by remember { mutableStateOf("") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 32.dp),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
            ) {
            Text(
                text = stringResource(R.string.shopping_list_add),
                style = MaterialTheme.typography.titleLarge,
            )
            TabRow(selectedTabIndex = selectedTab) {
                Tab(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    text = { Text(stringResource(R.string.shopping_list_buy_again)) },
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    text = { Text(stringResource(R.string.shopping_list_free_text)) },
                )
            }
            Spacer(Modifier.height(16.dp))
            if (selectedTab == 0) {
                when {
                    catalogOfflineEmpty -> {
                        Text(
                            text = stringResource(R.string.shopping_list_catalog_offline),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    recentProducts.isEmpty() -> {
                        Text(
                            text = stringResource(R.string.shopping_list_buy_again_empty),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier.height(320.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            items(recentProducts, key = { it.id }) { product ->
                                Surface(
                                    onClick = { onAddProduct(product.id) },
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .heightIn(min = 48.dp),
                                ) {
                                    Column(modifier = Modifier.padding(vertical = 12.dp)) {
                                        Text(
                                            text = product.displayName,
                                            style = MaterialTheme.typography.titleMedium,
                                        )
                                        product.packLabel?.let { pack ->
                                            Text(
                                                text = pack,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                    }
                                }
                                HorizontalDivider()
                            }
                        }
                    }
                }
            } else {
                OutlinedTextField(
                    value = freeText,
                    onValueChange = { freeText = it },
                    label = { Text(stringResource(R.string.shopping_list_free_text_hint)) },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                Button(
                    onClick = {
                        onAddFreeText(freeText)
                        freeText = ""
                        onDismiss()
                    },
                    enabled = freeText.isNotBlank(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp)
                        .height(48.dp),
                ) {
                    Text(stringResource(R.string.shopping_list_add))
                }
            }
            }
            snackbarHostState?.let { host ->
                SnackbarHost(
                    hostState = host,
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }
        }
    }
}
