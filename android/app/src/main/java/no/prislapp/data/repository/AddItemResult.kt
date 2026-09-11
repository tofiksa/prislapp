package no.prislapp.data.repository

import java.math.BigDecimal

data class AddItemResult(
    val itemId: String,
    val previousQuantity: BigDecimal? = null,
) {
    val merged: Boolean get() = previousQuantity != null
}
