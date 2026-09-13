package no.prislapp.data.upload

import no.prislapp.data.local.entity.PendingReceiptEntity
import java.util.concurrent.TimeUnit

object UnuploadedRetention {
    val MAX_AGE_WITHOUT_WARNING_MS: Long = TimeUnit.DAYS.toMillis(30)

    fun shouldShowBanner(receipts: List<PendingReceiptEntity>, nowMillis: Long): Boolean {
        val cutoff = nowMillis - MAX_AGE_WITHOUT_WARNING_MS
        return receipts.any { it.serverReceiptId == null && it.createdAt < cutoff }
    }
}
