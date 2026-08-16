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

    fun processing(localId: Long) = "processing/$localId"
    fun review(receiptId: String) = "review/$receiptId"
    fun productPrices(productId: String) = "product_prices/$productId"
}
