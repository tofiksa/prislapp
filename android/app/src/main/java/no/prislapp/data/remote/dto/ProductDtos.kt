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
