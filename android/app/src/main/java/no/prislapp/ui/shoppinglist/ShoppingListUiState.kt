package no.prislapp.ui.shoppinglist

import java.math.BigDecimal

data class ShoppingListUiState(
    val listId: String? = null,
    val listName: String = "",
    val items: List<ShoppingListItemUi> = emptyList(),
    val recentProducts: List<RecentProductUi> = emptyList(),
    val showConflictBanner: Boolean = false,
    val catalogOfflineEmpty: Boolean = false,
    val showAddSheet: Boolean = false,
    val pendingUndo: ShoppingListUndo? = null,
) {
    val undoSnackbarOnSheet: Boolean
        get() = showAddSheet && pendingUndo is ShoppingListUndo.RestoreQuantity
}

data class ShoppingListItemUi(
    val id: String,
    val displayName: String,
    val packLabel: String? = null,
    val quantity: BigDecimal = BigDecimal.ONE,
    val quantityLabel: String,
    val quantityUnit: String,
    val checked: Boolean,
    val noPriceHistory: Boolean,
    val userProductId: String?,
    val priceHistoryLabel: String? = if (noPriceHistory) "Ingen prishistorikk" else null,
)

data class RecentProductUi(
    val id: String,
    val displayName: String,
    val packLabel: String? = null,
    val quantityUnit: String,
)

sealed class ShoppingListUndo {
    data class RestoreQuantity(
        val itemId: String,
        val previousQuantity: BigDecimal,
    ) : ShoppingListUndo()

    data class Undelete(val itemId: String) : ShoppingListUndo()
}
