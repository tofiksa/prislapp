package no.prislapp.ui.shoppinglist

data class FirstReceiptCta(
    val readyCount: Int,
    val shouldShow: Boolean,
) {
    companion object {
        const val HISTORICAL_ITEM_THRESHOLD = 3

        fun evaluate(
            confirmedLineCount: Int,
            historicalItemCount: Int,
        ): FirstReceiptCta {
            val shouldShow = confirmedLineCount > 0 &&
                historicalItemCount < HISTORICAL_ITEM_THRESHOLD
            return FirstReceiptCta(
                readyCount = confirmedLineCount,
                shouldShow = shouldShow,
            )
        }
    }
}
