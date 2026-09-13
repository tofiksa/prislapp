package no.prislapp.data.upload

import no.prislapp.data.local.entity.PendingReceiptEntity
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.TimeUnit

class UnuploadedRetentionTest {
    private val now = 1_746_000_000_000L

    @Test
    fun bannerWhenUnuploadedOlderThanThirtyDays() {
        val old = PendingReceiptEntity(
            imagePath = "/old.jpg",
            userId = "a",
            createdAt = now - TimeUnit.DAYS.toMillis(31),
            serverReceiptId = null,
            status = "queued_offline",
        )
        assertTrue(UnuploadedRetention.shouldShowBanner(listOf(old), now))
    }

    @Test
    fun noBannerForRecentUnuploadedOrUploadedLeftovers() {
        val recent = PendingReceiptEntity(
            imagePath = "/recent.jpg",
            userId = "a",
            createdAt = now - TimeUnit.DAYS.toMillis(2),
            serverReceiptId = null,
            status = "queued_offline",
        )
        val leftover = PendingReceiptEntity(
            imagePath = "/leftover.jpg",
            userId = "a",
            createdAt = now - TimeUnit.DAYS.toMillis(40),
            serverReceiptId = "srv-1",
            status = "processing",
        )
        assertFalse(UnuploadedRetention.shouldShowBanner(listOf(recent, leftover), now))
    }
}
