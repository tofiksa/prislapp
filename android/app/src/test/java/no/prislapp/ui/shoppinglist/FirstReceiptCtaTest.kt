package no.prislapp.ui.shoppinglist

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FirstReceiptCtaTest {
    @Test
    fun showsWhenConfirmedLinesExistAndListHasFewerThanThreeHistoricalItems() {
        val cta = FirstReceiptCta.evaluate(
            confirmedLineCount = 4,
            historicalItemCount = 0,
        )
        assertTrue(cta.shouldShow)
        assertEquals(4, cta.readyCount)
    }

    @Test
    fun hiddenWhenActiveListAlreadyHasThreeHistoricalItems() {
        val cta = FirstReceiptCta.evaluate(
            confirmedLineCount = 5,
            historicalItemCount = 3,
        )
        assertFalse(cta.shouldShow)
    }

    @Test
    fun hiddenWhenConfirmHasNoLines() {
        val cta = FirstReceiptCta.evaluate(
            confirmedLineCount = 0,
            historicalItemCount = 0,
        )
        assertFalse(cta.shouldShow)
    }
}
