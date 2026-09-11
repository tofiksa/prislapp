package no.prislapp.data.remote.dto

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PriceSummaryDtoTest {
    private val gson = Gson()

    @Test
    fun fixtureAmountsStayDecimalStringsAndNullLowestIsNotZero() {
        val summary = gson.fromJson(FIXTURE_JSON, ShoppingListPriceSummaryDto::class.java)

        val lowest = summary.lines[0].historical_lowest
        assertEquals("24.90", lowest?.amount)
        assertTrue(lowest?.amount is String)
        assertEquals("per_package", lowest?.price_basis)

        val missing = summary.lines[1]
        assertNull(missing.historical_lowest)
        assertEquals("no_comparable_price", missing.status)
        assertEquals("free_text_no_history", missing.reason)
        val encoded = gson.toJson(missing)
        assertTrue(!encoded.contains("\"0.00\""))
        assertTrue(!encoded.contains("\"0,00\""))
    }

    companion object {
        private val FIXTURE_JSON = """
            {
              "list_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              "list_version": 7,
              "content_revision": 31,
              "price_data_version": 12,
              "calculated_at": "2026-09-11T07:00:00Z",
              "policy_version": "p0-2026-09-11",
              "include_conditional": false,
              "lines": [
                {
                  "item_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                  "product_id": "11111111-1111-4111-8111-111111111111",
                  "free_text": null,
                  "status": "historical_lowest",
                  "reason": null,
                  "quantity": "1.000",
                  "quantity_unit": "each",
                  "eligible_store_count": 2,
                  "historical_lowest": {
                    "amount": "24.90",
                    "store_id": "22222222-2222-4222-8222-222222222222",
                    "store_name": "Rema 1000 Majorstuen",
                    "identity_level": "branch",
                    "purchase_date": "2026-09-08",
                    "age_label": "registrert nylig",
                    "price_basis": "per_package",
                    "disclaimer": "Dagens pris kan være annerledes"
                  }
                },
                {
                  "item_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                  "product_id": null,
                  "free_text": "Melk",
                  "status": "no_comparable_price",
                  "reason": "free_text_no_history",
                  "quantity": "1.000",
                  "quantity_unit": "each",
                  "eligible_store_count": 0,
                  "historical_lowest": null
                }
              ]
            }
        """.trimIndent()
    }
}
