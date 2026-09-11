package no.prislapp.ui.shoppinglist

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import no.prislapp.data.local.entity.CachedUserProductEntity
import no.prislapp.data.local.entity.ShoppingListEntity
import no.prislapp.data.local.entity.ShoppingListItemEntity
import no.prislapp.data.local.entity.SyncConflictEntity
import no.prislapp.data.repository.ShoppingListRepository
import no.prislapp.domain.QuantityFormat
import java.math.BigDecimal
import javax.inject.Inject

@HiltViewModel
class ShoppingListViewModel @Inject constructor(
    private val repository: ShoppingListRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ShoppingListUiState())
    val uiState: StateFlow<ShoppingListUiState> = _uiState.asStateFlow()
    private val writeMutex = Mutex()
    private var defaultListRequested = false

    @Volatile
    private var catalogRefreshFailed = false

    init {
        observeList()
        refreshRecent()
    }

    fun refresh() {
        refreshRecent()
    }

    fun addRecentProduct(productId: String) {
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                val product = _uiState.value.recentProducts.find { it.id == productId } ?: return@withLock
                val unit = if (product.quantityUnit == "unknown") "each" else product.quantityUnit
                val result = repository.addProductOrIncrement(
                    listId = listId,
                    userProductId = product.id,
                    productDisplayName = product.displayName,
                    quantity = BigDecimal.ONE,
                    quantityUnit = unit,
                )
                if (result.previousQuantity != null) {
                    _uiState.update {
                        it.copy(
                            pendingUndo = ShoppingListUndo.RestoreQuantity(
                                itemId = result.itemId,
                                previousQuantity = result.previousQuantity,
                            ),
                        )
                    }
                }
            }
        }
    }

    fun addFreeText(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                repository.addItem(
                    listId = listId,
                    freeText = trimmed,
                    userProductId = null,
                    productDisplayName = null,
                    quantity = BigDecimal.ONE,
                    quantityUnit = "each",
                )
            }
        }
    }

    fun setChecked(itemId: String, checked: Boolean) {
        viewModelScope.launch {
            val listId = _uiState.value.listId ?: return@launch
            repository.setItemChecked(listId, itemId, checked)
        }
    }

    fun incrementQuantity(itemId: String) {
        changeQuantity(itemId, BigDecimal.ONE)
    }

    fun decrementQuantity(itemId: String) {
        changeQuantity(itemId, BigDecimal.ONE.negate())
    }

    fun deleteItem(itemId: String) {
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                repository.setItemDeleted(listId, itemId, true)
                _uiState.update { it.copy(pendingUndo = ShoppingListUndo.Undelete(itemId)) }
            }
        }
    }

    fun undo() {
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                when (val undo = _uiState.value.pendingUndo) {
                    is ShoppingListUndo.RestoreQuantity ->
                        repository.setItemQuantity(listId, undo.itemId, undo.previousQuantity)
                    is ShoppingListUndo.Undelete ->
                        repository.setItemDeleted(listId, undo.itemId, false)
                    null -> return@withLock
                }
                _uiState.update { it.copy(pendingUndo = null) }
            }
        }
    }

    fun dismissUndo() {
        _uiState.update { it.copy(pendingUndo = null) }
    }

    private fun changeQuantity(itemId: String, delta: BigDecimal) {
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                val item = _uiState.value.items.find { it.id == itemId } ?: return@withLock
                val next = item.quantity + delta
                val minimum = if (item.quantityUnit == "each") BigDecimal.ONE else QuantityFormat.fromJson("0.001")
                if (next < minimum) return@withLock
                repository.setItemQuantity(listId, itemId, next)
            }
        }
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private fun observeList() {
        viewModelScope.launch {
            repository.observeLists()
                .map { lists -> lists.filter { it.status == ShoppingListEntity.STATUS_ACTIVE && !it.deleted } }
                .distinctUntilChanged()
                .flatMapLatest { lists ->
                    if (lists.isEmpty()) {
                        if (!defaultListRequested) {
                            defaultListRequested = true
                            val id = repository.createList(DEFAULT_LIST_NAME)
                            _uiState.update { it.copy(listId = id, listName = DEFAULT_LIST_NAME) }
                        }
                        combine(
                            repository.observeConflicts(),
                            repository.observeRecentProducts(),
                        ) { conflicts, products ->
                            buildState(list = null, items = emptyList(), conflicts, products)
                        }
                    } else {
                        val selected = lists.first()
                        combine(
                            repository.observeItems(selected.id),
                            repository.observeConflicts(),
                            repository.observeRecentProducts(),
                        ) { items, conflicts, products ->
                            buildState(selected, items, conflicts, products)
                        }
                    }
                }
                .collect { mapped ->
                    _uiState.update { previous ->
                        mapped.copy(
                            listId = mapped.listId ?: previous.listId,
                            listName = mapped.listName.ifEmpty { previous.listName },
                            pendingUndo = previous.pendingUndo,
                        )
                    }
                }
        }
    }

    private fun refreshRecent() {
        viewModelScope.launch {
            try {
                repository.refreshRecentProducts()
                catalogRefreshFailed = false
                _uiState.update { it.copy(catalogOfflineEmpty = false) }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                catalogRefreshFailed = true
                _uiState.update { it.copy(catalogOfflineEmpty = it.recentProducts.isEmpty()) }
            }
        }
    }

    private fun buildState(
        list: ShoppingListEntity?,
        items: List<ShoppingListItemEntity>,
        conflicts: List<SyncConflictEntity>,
        products: List<CachedUserProductEntity>,
    ): ShoppingListUiState {
        val byId = products.associateBy { it.id }
        val visible = items.filter { !it.deleted }
        val sorted = visible.sortedWith(compareBy<ShoppingListItemEntity> { it.checked }.thenBy { it.position })
        return ShoppingListUiState(
            listId = list?.id,
            listName = list?.name.orEmpty(),
            items = sorted.map { item ->
                val cached = item.userProductId?.let { byId[it] }
                val noPriceHistory = item.userProductId == null
                ShoppingListItemUi(
                    id = item.id,
                    displayName = item.freeText ?: cached?.displayName ?: FALLBACK_NAME,
                    packLabel = packLabel(cached?.packContent, cached?.packUnit ?: item.quantityUnit),
                    quantity = QuantityFormat.fromJson(item.quantity),
                    quantityLabel = quantityLabel(item.quantity, item.quantityUnit),
                    quantityUnit = item.quantityUnit,
                    checked = item.checked,
                    noPriceHistory = noPriceHistory,
                    userProductId = item.userProductId,
                    priceHistoryLabel = if (noPriceHistory) NO_PRICE_HISTORY else null,
                )
            },
            recentProducts = products.map { product ->
                RecentProductUi(
                    id = product.id,
                    displayName = product.displayName,
                    packLabel = packLabel(product.packContent, product.packUnit),
                    quantityUnit = product.packUnit,
                )
            },
            showConflictBanner = conflicts.isNotEmpty(),
            catalogOfflineEmpty = catalogRefreshFailed && products.isEmpty(),
        )
    }

    companion object {
        const val DEFAULT_LIST_NAME = "Handleliste"
        const val NO_PRICE_HISTORY = "Ingen prishistorikk"
        private const val FALLBACK_NAME = "Vare"
    }
}

internal fun packLabel(content: String?, unit: String?): String? {
    val resolved = unit ?: return null
    if (resolved == "unknown") return null
    val unitLabel = if (resolved == "each") "stk" else resolved
    if (content.isNullOrBlank()) return if (resolved == "each") null else unitLabel
    val number = runCatching {
        QuantityFormat.fromJson(content).stripTrailingZeros().toPlainString().replace('.', ',')
    }.getOrElse { content.replace('.', ',') }
    return "$number $unitLabel"
}

internal fun quantityLabel(quantity: String, unit: String): String {
    val number = QuantityFormat.fromJson(quantity).stripTrailingZeros().toPlainString().replace('.', ',')
    return if (unit == "each") number else "$number $unit"
}
