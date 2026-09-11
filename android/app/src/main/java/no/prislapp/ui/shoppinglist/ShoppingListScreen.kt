package no.prislapp.ui.shoppinglist

import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.semantics.contentDescription
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
    firstReceiptReadyCount: Int? = null,
    onLogout: () -> Unit = {},
    viewModel: ShoppingListViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val listSnackbarHostState = remember { SnackbarHostState() }
    val sheetSnackbarHostState = remember { SnackbarHostState() }
    var accountMenuExpanded by remember { mutableStateOf(false) }
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

    LaunchedEffect(firstReceiptReadyCount) {
        val count = firstReceiptReadyCount ?: return@LaunchedEffect
        viewModel.applyFirstReceiptCta(count)
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.shopping_list_title),
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
            uiState.firstReceiptCtaCount?.let { readyCount ->
                Surface(
                    color = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = stringResource(R.string.first_receipt_cta_title, readyCount),
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Button(
                            onClick = viewModel::acceptFirstReceiptCta,
                            modifier = Modifier
                                .padding(top = 8.dp)
                                .height(48.dp),
                        ) {
                            Text(stringResource(R.string.first_receipt_cta_action))
                        }
                    }
                }
            }
            uiState.pricesFetchedAtLabel?.let { fetched ->
                Text(
                    text = fetched,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            if (uiState.priceRefreshFailed) {
                Text(
                    text = stringResource(R.string.shopping_list_price_refresh_failed),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp),
                )
                TextButton(
                    onClick = viewModel::refreshPrices,
                    modifier = Modifier.height(48.dp),
                ) {
                    Text(stringResource(R.string.shopping_list_price_retry))
                }
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
                            onPriceClick = { viewModel.openPriceDetail(item.id) },
                            onRetryPrice = viewModel::refreshPrices,
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

    uiState.priceDetail?.let { detail ->
        PriceDetailSheet(
            detail = detail,
            onDismiss = viewModel::dismissPriceDetail,
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
    onPriceClick: () -> Unit,
    onRetryPrice: () -> Unit,
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
                val details = listOfNotNull(item.packLabel, item.quantityLabel).joinToString(" · ")
                if (details.isNotBlank()) {
                    Text(
                        text = details,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                item.priceLabel?.let { price ->
                    val priceDescription = item.priceContentDescription ?: price
                    Text(
                        text = price,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .clickable(onClick = onPriceClick)
                            .semantics { contentDescription = priceDescription },
                    )
                }
                if (item.showPriceRetry) {
                    TextButton(
                        onClick = onRetryPrice,
                        modifier = Modifier.height(48.dp),
                    ) {
                        Text(stringResource(R.string.shopping_list_price_retry))
                    }
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PriceDetailSheet(
    detail: PriceDetailUi,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .padding(bottom = 32.dp),
        ) {
            Text(
                text = stringResource(R.string.shopping_list_price_detail_title),
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                text = detail.title,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp),
            )
            if (detail.lines.isEmpty()) {
                Text(
                    text = PriceSummaryCopy.NO_COMPARABLE,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )
            } else {
                detail.lines.forEach { line ->
                    Text(
                        text = line,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }
            }
            detail.disclaimer?.let { disclaimer ->
                Text(
                    text = disclaimer,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 12.dp),
                )
            }
            detail.receiptId?.let { receiptId ->
                Text(
                    text = stringResource(R.string.shopping_list_price_receipt, receiptId),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier
                    .padding(top = 16.dp)
                    .height(48.dp),
            ) {
                Text(stringResource(R.string.shopping_list_close_price_detail))
            }
        }
    }
}
