package no.prislapp.ui.shoppinglist

import no.prislapp.data.remote.dto.ShoppingListPriceSummaryLineDto
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryLowestDto
import no.prislapp.ui.components.formatReceiptSubtitle

internal object PriceSummaryCopy {
    const val FETCHING = "Henter pris…"
    const val FETCH_FAILED = "Kunne ikke hente pris"
    const val AWAITING_SYNC = "Pris oppdateres etter synkronisering"
    const val NO_COMPARABLE = "Ingen sammenlignbar pris"
    const val NO_PRICE_HISTORY = "Ingen prishistorikk"
    const val DISCLAIMER = "Dagens pris kan være annerledes"
    const val FETCHED_AT_PREFIX = "Priser hentet"

    fun fetchedAtLabel(iso: String): String? {
        val date = formatReceiptSubtitle(iso, null).takeIf { it.isNotBlank() } ?: return null
        return "$FETCHED_AT_PREFIX $date"
    }

    fun lineLabel(line: ShoppingListPriceSummaryLineDto): String {
        val lowest = line.historical_lowest
        if (lowest == null) return noComparableLabel(line.reason)
        val amount = formatAmount(lowest.amount)
        val meta = meta(lowest)
        val main = if (line.eligible_store_count == 1) {
            "Registrert hos ${lowest.store_name} — ingen butikksammenligning ennå · $amount kr"
        } else {
            "Lavest registrert: $amount kr hos ${lowest.store_name}"
        }
        return if (meta.isEmpty()) main else "$main · $meta"
    }

    fun noComparableLabel(reason: String?): String {
        if (reason == "free_text_no_history") return NO_PRICE_HISTORY
        val detail = reasonLabel(reason)
        return if (detail == null) NO_COMPARABLE else "$NO_COMPARABLE · $detail"
    }

    fun formatAmount(amount: String): String = amount.replace('.', ',')

    fun detailLines(line: ShoppingListPriceSummaryLineDto?): List<String> {
        val lowest = line?.historical_lowest ?: return emptyList()
        val rows = mutableListOf(
            "${formatAmount(lowest.amount)} kr hos ${lowest.store_name}",
        )
        meta(lowest).takeIf { it.isNotEmpty() }?.let { rows.add(it) }
        for (tied in lowest.tied_stores) {
            if (tied.store_id == lowest.store_id) continue
            val date = formatReceiptSubtitle(tied.purchase_date, null)
            rows.add(
                listOfNotNull(tied.store_name, date.takeIf { it.isNotBlank() }).joinToString(" · "),
            )
        }
        return rows
    }

    fun priceBasisLabel(basis: String): String? = when (basis) {
        "per_package" -> "per pakke"
        "per_kg" -> "kr/kg"
        "per_litre" -> "kr/l"
        else -> null
    }

    fun reasonLabel(reason: String?): String? = when (reason) {
        "free_text_no_history" -> NO_PRICE_HISTORY
        "never_observed" -> "Aldri registrert"
        "no_qualified_observation" -> "Ingen kvalifisert observasjon"
        "unknown_unit" -> "Ukjent enhet"
        else -> null
    }

    private fun meta(lowest: ShoppingListPriceSummaryLowestDto): String {
        return listOfNotNull(
            formatReceiptSubtitle(lowest.purchase_date, null).takeIf { it.isNotBlank() },
            lowest.age_label.takeIf { it.isNotBlank() },
            priceBasisLabel(lowest.price_basis),
        ).joinToString(" · ")
    }
}
