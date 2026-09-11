package no.prislapp.ui.navigation

object Routes {
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val HOME = "home"
    const val CAMERA = "camera"
    const val PROCESSING = "processing/{localId}"
    const val REVIEW = "review/{receiptId}"
    const val HISTORY = "history"
    const val PRODUCT_SEARCH = "product_search"
    const val PRODUCT_PRICES = "product_prices/{productId}"
    const val SHOPPING_LIST = "shopping_list"
    const val RECEIPTS = "receipts"
    const val LOGGED_IN_START = SHOPPING_LIST

    val TAB_ROUTES = setOf(SHOPPING_LIST, PRODUCT_SEARCH, RECEIPTS)

    fun processing(localId: Long) = "processing/$localId"
    fun review(receiptId: String) = "review/$receiptId"
    fun productPrices(productId: String) = "product_prices/$productId"
}
