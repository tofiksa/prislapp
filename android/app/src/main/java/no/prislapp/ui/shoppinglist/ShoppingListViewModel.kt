package no.prislapp.ui.shoppinglist

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
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
import kotlinx.coroutines.withTimeout
import no.prislapp.data.local.entity.CachedUserProductEntity
import no.prislapp.data.local.entity.ShoppingListEntity
import no.prislapp.data.local.entity.ShoppingListItemEntity
import no.prislapp.data.local.entity.SyncConflictEntity
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryDto
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryLineDto
import no.prislapp.data.repository.PriceSummaryRepository
import no.prislapp.data.repository.ReceiptRepository
import no.prislapp.data.repository.ShoppingListRepository
import no.prislapp.domain.QuantityFormat
import java.math.BigDecimal
import java.time.Instant
import javax.inject.Inject

@HiltViewModel
class ShoppingListViewModel @Inject constructor(
    private val repository: ShoppingListRepository,
    private val priceSummaryRepository: PriceSummaryRepository,
    private val receiptRepository: ReceiptRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ShoppingListUiState())
    val uiState: StateFlow<ShoppingListUiState> = _uiState.asStateFlow()
    private val writeMutex = Mutex()
    private var defaultListRequested = false
    private var hadActiveList = false
    private var finishInFlight = false

    @Volatile
    private var catalogRefreshFailed = false

    private var latestList: ShoppingListEntity? = null
    private var latestItems: List<ShoppingListItemEntity> = emptyList()
    private var latestConflicts: List<SyncConflictEntity> = emptyList()
    private var latestProducts: List<CachedUserProductEntity> = emptyList()
    private var displayedSummary: ShoppingListPriceSummaryDto? = null
    private var displayedFetchedAt: String? = null
    private var displayedFromCache: Boolean = false
    private var displayedCalculatedAt: Instant? = null
    private var displayedContentRevision: Int? = null
    private var displayedListVersion: Int? = null
    private var displayedPriceDataVersion: Int? = null
    private var priceLoading = false
    private var priceFetchFailed = false
    private var observedListId: String? = null
    private var lastRefreshedContentRevision: Int? = null
    private var priceJob: Job? = null

    init {
        receiptRepository.resumePendingWork()
        repository.resumePendingWork()
        observeList()
        refreshRecent()
    }

    fun refresh() {
        refreshRecent()
        refreshPrices()
    }

    fun refreshPrices() {
        val listId = _uiState.value.listId ?: latestList?.id ?: return
        priceJob?.cancel()
        priceJob = viewModelScope.launch {
            loadPrices(listId)
        }
    }

    fun openAddSheet() {
        _uiState.update { it.copy(showAddSheet = true) }
    }

    fun dismissAddSheet() {
        _uiState.update { it.copy(showAddSheet = false) }
    }

    fun applyFirstReceiptCta(confirmedLineCount: Int) {
        val historical = _uiState.value.items.count { it.userProductId != null }
        val cta = FirstReceiptCta.evaluate(confirmedLineCount, historical)
        if (cta.shouldShow) {
            _uiState.update { it.copy(firstReceiptCtaCount = cta.readyCount) }
            refreshRecent()
        }
    }

    fun acceptFirstReceiptCta() {
        _uiState.update { it.copy(firstReceiptCtaCount = null, showAddSheet = true) }
        refreshRecent()
    }

    fun dismissFirstReceiptCta() {
        _uiState.update { it.copy(firstReceiptCtaCount = null) }
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

    fun finishTrip(keepUnchecked: Boolean) {
        if (finishInFlight) return
        finishInFlight = true
        viewModelScope.launch {
            writeMutex.withLock {
                try {
                    val listId = _uiState.value.listId ?: return@withLock
                    val newId = repository.finishTrip(listId, keepUnchecked)
                    _uiState.update { it.copy(listId = newId, showAddReceiptPrompt = true) }
                } finally {
                    finishInFlight = false
                }
            }
        }
    }

    fun dismissAddReceiptPrompt() {
        _uiState.update { it.copy(showAddReceiptPrompt = false) }
    }

    fun copyCurrentList() {
        viewModelScope.launch {
            writeMutex.withLock {
                val listId = _uiState.value.listId ?: return@withLock
                val newId = repository.copyList(listId)
                _uiState.update { it.copy(listId = newId) }
            }
        }
    }

    fun newList() {
        viewModelScope.launch {
            writeMutex.withLock {
                val id = repository.createList(DEFAULT_LIST_NAME)
                _uiState.update { it.copy(listId = id, listName = DEFAULT_LIST_NAME) }
            }
        }
    }

    fun openPriceDetail(itemId: String) {
        val item = _uiState.value.items.find { it.id == itemId } ?: return
        val line = displayedSummary?.lines?.find { it.item_id == itemId }
        val lowest = line?.historical_lowest
        _uiState.update {
            it.copy(
                priceDetail = PriceDetailUi(
                    itemId = itemId,
                    title = item.displayName,
                    lines = PriceSummaryCopy.detailLines(line),
                    disclaimer = lowest?.disclaimer ?: if (lowest != null) PriceSummaryCopy.DISCLAIMER else null,
                    receiptId = lowest?.receipt_id,
                ),
            )
        }
    }

    fun dismissPriceDetail() {
        _uiState.update { it.copy(priceDetail = null) }
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
                        if (hadActiveList) {
                            defaultListRequested = false
                            hadActiveList = false
                        }
                        if (!defaultListRequested) {
                            defaultListRequested = true
                            val id = repository.createList(DEFAULT_LIST_NAME)
                            _uiState.update { it.copy(listId = id, listName = DEFAULT_LIST_NAME) }
                        }
                        combine(
                            repository.observeConflicts(),
                            repository.observeRecentProducts(),
                        ) { conflicts, products ->
                            Triple(null as ShoppingListEntity?, emptyList<ShoppingListItemEntity>(), Pair(conflicts, products))
                        }
                    } else {
                        hadActiveList = true
                        defaultListRequested = true
                        val selected = lists.maxWith(
                            compareBy<ShoppingListEntity> { it.createdAt }.thenBy { it.updatedAt },
                        )
                        combine(
                            repository.observeItems(selected.id),
                            repository.observeConflicts(),
                            repository.observeRecentProducts(),
                        ) { items, conflicts, products ->
                            Triple(selected, items, Pair(conflicts, products))
                        }
                    }
                }
                .collect { (list, items, extras) ->
                    val (conflicts, products) = extras
                    latestList = list
                    latestItems = items
                    latestConflicts = conflicts
                    latestProducts = products
                    val mapped = buildState(list, items, conflicts, products)
                    _uiState.update { previous ->
                        mapped.copy(
                            listId = mapped.listId ?: previous.listId,
                            listName = mapped.listName.ifEmpty { previous.listName },
                            pendingUndo = previous.pendingUndo,
                            showAddSheet = previous.showAddSheet,
                            priceDetail = previous.priceDetail,
                            firstReceiptCtaCount = previous.firstReceiptCtaCount,
                            showAddReceiptPrompt = previous.showAddReceiptPrompt,
                        )
                    }
                    val listId = mapped.listId ?: _uiState.value.listId
                    val revision = list?.contentRevision
                    if (listId != null && (listId != observedListId || revision != lastRefreshedContentRevision)) {
                        observedListId = listId
                        lastRefreshedContentRevision = revision
                        refreshPrices()
                    }
                }
        }
    }

    private suspend fun loadPrices(listId: String) {
        if (displayedSummary == null) {
            priceLoading = true
            priceFetchFailed = false
            publishPrices()
        }
        val cached = runCatching { priceSummaryRepository.cached(listId) }.getOrNull()
        if (cached != null && shouldApply(cached.summary)) {
            applySummary(cached.summary, cached.fetchedAt, fromCache = true)
            priceLoading = false
            publishPrices()
        }
        try {
            val fresh = withTimeout(PRICE_FETCH_TIMEOUT_MS) {
                priceSummaryRepository.refresh(listId)
            }
            if (shouldApply(fresh)) {
                applySummary(fresh, Instant.now().toString(), fromCache = false)
            }
            priceFetchFailed = false
        } catch (e: TimeoutCancellationException) {
            priceFetchFailed = true
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            priceFetchFailed = true
        } finally {
            priceLoading = false
            publishPrices()
        }
    }

    private fun shouldApply(summary: ShoppingListPriceSummaryDto): Boolean {
        val listRevision = latestList?.contentRevision ?: 0
        if (summary.content_revision < listRevision) return false
        displayedContentRevision?.let { if (summary.content_revision < it) return false }
        displayedCalculatedAt?.let { shown ->
            val incoming = runCatching { Instant.parse(summary.calculated_at) }.getOrNull()
            if (incoming != null && incoming.isBefore(shown)) return false
        }
        if (displayedContentRevision == summary.content_revision) {
            displayedListVersion?.let { if (summary.list_version < it) return false }
            displayedPriceDataVersion?.let { if (summary.price_data_version < it) return false }
        }
        return true
    }

    private fun applySummary(
        summary: ShoppingListPriceSummaryDto,
        fetchedAt: String,
        fromCache: Boolean,
    ) {
        displayedSummary = summary
        displayedFetchedAt = fetchedAt
        displayedFromCache = fromCache
        displayedCalculatedAt = runCatching { Instant.parse(summary.calculated_at) }.getOrNull()
        displayedContentRevision = summary.content_revision
        displayedListVersion = summary.list_version
        displayedPriceDataVersion = summary.price_data_version
    }

    private fun publishPrices() {
        val mapped = buildState(latestList, latestItems, latestConflicts, latestProducts)
        _uiState.update { previous ->
            mapped.copy(
                listId = mapped.listId ?: previous.listId,
                listName = mapped.listName.ifEmpty { previous.listName },
                pendingUndo = previous.pendingUndo,
                showAddSheet = previous.showAddSheet,
                priceDetail = previous.priceDetail,
                firstReceiptCtaCount = previous.firstReceiptCtaCount,
                showAddReceiptPrompt = previous.showAddReceiptPrompt,
            )
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
        val summary = displayedSummary
        val summaryIds = summary?.lines?.map { it.item_id }?.toSet().orEmpty()
        val visibleIds = sorted.map { it.id }.toSet()
        val assortmentChanged = summary != null && !summaryIds.containsAll(visibleIds)
        val keepCacheError = priceFetchFailed && summary != null && !assortmentChanged
        return ShoppingListUiState(
            listId = list?.id,
            listName = list?.name.orEmpty(),
            items = sorted.map { item ->
                val cached = item.userProductId?.let { byId[it] }
                val noPriceHistory = item.userProductId == null
                val line = summary?.lines?.find { it.item_id == item.id }
                val priced = overlayPrice(line, noPriceHistory, assortmentChanged)
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
                    priceLabel = priced.label,
                    priceContentDescription = priced.label,
                    showPriceRetry = priced.retry,
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
            pricesFetchedAtLabel = if (displayedFromCache) {
                displayedFetchedAt?.let(PriceSummaryCopy::fetchedAtLabel)
            } else {
                null
            },
            priceRefreshFailed = keepCacheError,
        )
    }

    private fun overlayPrice(
        line: ShoppingListPriceSummaryLineDto?,
        noPriceHistory: Boolean,
        assortmentChanged: Boolean,
    ): Overlay {
        if (assortmentChanged) {
            return Overlay(PriceSummaryCopy.AWAITING_SYNC, retry = false)
        }
        if (line != null) {
            return Overlay(PriceSummaryCopy.lineLabel(line), retry = false)
        }
        if (priceLoading) {
            return Overlay(PriceSummaryCopy.FETCHING, retry = false)
        }
        if (priceFetchFailed && displayedSummary == null) {
            return Overlay(PriceSummaryCopy.FETCH_FAILED, retry = true)
        }
        if (noPriceHistory) {
            return Overlay(PriceSummaryCopy.NO_PRICE_HISTORY, retry = false)
        }
        if (priceFetchFailed) {
            return Overlay(PriceSummaryCopy.FETCH_FAILED, retry = true)
        }
        return Overlay(PriceSummaryCopy.FETCHING, retry = false)
    }

    private data class Overlay(val label: String?, val retry: Boolean)

    companion object {
        const val DEFAULT_LIST_NAME = "Handleliste"
        const val NO_PRICE_HISTORY = "Ingen prishistorikk"
        const val PRICE_FETCH_TIMEOUT_MS = 15_000L
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
