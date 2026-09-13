package no.prislapp.data.remote.dto

import java.math.BigDecimal

data class ProductSummaryResponse(
    val id: String,
    val canonical_name: String,
    val category: String? = null,
)

data class ProductSearchResponse(
    val items: List<ProductSummaryResponse>,
)

data class PriceObservationResponse(
    val store: StoreResponse,
    val price: BigDecimal,
    val observed_at: String,
)

data class LatestStorePriceResponse(
    val store: StoreResponse,
    val price: BigDecimal,
    val observed_at: String,
)

data class ProductPricesResponse(
    val product: ProductSummaryResponse,
    val cheapest: PriceObservationResponse?,
    val observations: List<PriceObservationResponse>,
    val latest_by_store: List<LatestStorePriceResponse>,
)

data class StoreListResponse(
    val items: List<StoreResponse>,
)

data class UserProductResponse(
    val id: String,
    val display_name: String,
    val brand: String? = null,
    val variant: String? = null,
    val pack_content: String? = null,
    val pack_unit: String,
    val pack_count: String? = null,
    val identity_status: String,
    val last_purchased_at: String? = null,
    val purchase_count: Int = 0,
    val version: Int = 1,
)

data class UserProductListResponse(
    val items: List<UserProductResponse>,
    val next_cursor: String? = null,
)
