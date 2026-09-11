package no.prislapp.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal
import java.time.ZoneId

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

    @Test
    fun formatsCaptureTimeInOslo() {
        val millis = java.time.OffsetDateTime.parse("2026-08-11T10:15:00+02:00").toInstant().toEpochMilli()
        assertEquals("11.08.2026 10:15", formatCaptureTime(millis, ZoneId.of("Europe/Oslo")))
    }
}
