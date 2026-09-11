package no.prislapp.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class ReceiptRowFormatTest {
    @Test
    fun formatsDateAndTotal() {
        assertEquals(
            "11.08.2026 · 25,90 kr",
            formatReceiptSubtitle("2026-08-11T10:00:00Z", BigDecimal("25.90")),
        )
    }

    @Test
    fun omitsMissingParts() {
        assertEquals("", formatReceiptSubtitle(null, null))
        assertEquals("25,90 kr", formatReceiptSubtitle(null, BigDecimal("25.90")))
    }

    @Test
    fun convertsOsloMidnightStoredAsUtc() {
        assertEquals("11.08.2026", formatReceiptSubtitle("2026-08-10T22:00:00Z", null))
    }

    @Test
    fun omitsMalformedDate() {
        assertEquals("", formatReceiptSubtitle("not-a-date", null))
    }
}
