package no.prislapp.domain

import java.math.BigDecimal
import java.math.RoundingMode

object QuantityFormat {
    private const val SCALE = 3

    fun toJson(value: BigDecimal): String =
        value.setScale(SCALE, RoundingMode.HALF_UP).toPlainString()

    fun fromJson(value: String): BigDecimal = BigDecimal(value)
}
