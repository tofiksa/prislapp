package no.prislapp.data.repository

import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ProductPricesResponse
import no.prislapp.data.remote.dto.ProductSearchResponse
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ProductRepository @Inject constructor(
    private val api: PrislappApi,
) {
    suspend fun searchProducts(query: String): ProductSearchResponse {
        return api.searchProducts(query)
    }

    suspend fun getProductPrices(productId: String): ProductPricesResponse {
        return api.getProductPrices(productId)
    }
}
