package no.prislapp.ui.receipt

import no.prislapp.R
import org.junit.Assert.assertEquals
import org.junit.Test

class ReceiptStatusCopyTest {
    @Test
    fun mapsKnownStatuses() {
        assertEquals(R.string.status_pending, receiptStatusLabelRes("PENDING"))
        assertEquals(R.string.status_uploading, receiptStatusLabelRes("UPLOADING"))
        assertEquals(R.string.status_uploaded, receiptStatusLabelRes("UPLOADED"))
        assertEquals(R.string.status_processing, receiptStatusLabelRes("PROCESSING"))
        assertEquals(R.string.status_ready, receiptStatusLabelRes("READY_FOR_REVIEW"))
        assertEquals(R.string.status_failed, receiptStatusLabelRes("FAILED"))
        assertEquals(R.string.status_confirmed, receiptStatusLabelRes("CONFIRMED"))
    }

    @Test
    fun unknownStatusUsesFallbackResource() {
        assertEquals(R.string.status_unknown, receiptStatusLabelRes("SOMETHING_ELSE"))
    }
}
