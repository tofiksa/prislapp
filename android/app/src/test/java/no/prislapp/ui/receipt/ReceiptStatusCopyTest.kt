package no.prislapp.ui.receipt

import no.prislapp.R
import org.junit.Assert.assertEquals
import org.junit.Test

class ReceiptStatusCopyTest {
    @Test
    fun mapsKnownStatuses() {
        assertEquals(R.string.status_queued_offline, receiptStatusLabelRes("queued_offline"))
        assertEquals(R.string.status_queued_offline, receiptStatusLabelRes("PENDING"))
        assertEquals(R.string.status_uploading, receiptStatusLabelRes("uploading"))
        assertEquals(R.string.status_uploading, receiptStatusLabelRes("UPLOADING"))
        assertEquals(R.string.status_processing, receiptStatusLabelRes("processing"))
        assertEquals(R.string.status_processing, receiptStatusLabelRes("PROCESSING"))
        assertEquals(R.string.status_processing, receiptStatusLabelRes("UPLOADED"))
        assertEquals(R.string.status_ready, receiptStatusLabelRes("ready_for_review"))
        assertEquals(R.string.status_ready, receiptStatusLabelRes("READY_FOR_REVIEW"))
        assertEquals(R.string.status_needs_action, receiptStatusLabelRes("needs_action"))
        assertEquals(R.string.status_failed_permanent, receiptStatusLabelRes("failed_permanent"))
        assertEquals(R.string.status_confirmed, receiptStatusLabelRes("CONFIRMED"))
    }

    @Test
    fun unknownStatusUsesFallbackResource() {
        assertEquals(R.string.status_unknown, receiptStatusLabelRes("SOMETHING_ELSE"))
    }
}
