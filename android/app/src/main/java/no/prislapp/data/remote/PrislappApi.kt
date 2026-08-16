package no.prislapp.data.remote

import no.prislapp.data.remote.dto.GoogleAuthRequest
import no.prislapp.data.remote.dto.LoginRequest
import no.prislapp.data.remote.dto.ProductPricesResponse
import no.prislapp.data.remote.dto.ProductSearchResponse
import no.prislapp.data.remote.dto.ReceiptConfirmRequest
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.remote.dto.ReceiptListResponse
import no.prislapp.data.remote.dto.ReceiptUploadResponse
import no.prislapp.data.remote.dto.RegisterRequest
import no.prislapp.data.remote.dto.StoreListResponse
import no.prislapp.data.remote.dto.TokenResponse
import no.prislapp.data.remote.dto.UserResponse
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface PrislappApi {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("auth/google")
    suspend fun googleAuth(@Body body: GoogleAuthRequest): TokenResponse

    @GET("auth/me")
    suspend fun getMe(): UserResponse

    @Multipart
    @POST("receipts")
    suspend fun uploadReceipt(@Part file: MultipartBody.Part): ReceiptUploadResponse

    @GET("receipts")
    suspend fun listReceipts(
        @Query("page") page: Int = 1,
        @Query("store_id") storeId: String? = null,
        @Query("status") status: String? = null,
    ): ReceiptListResponse

    @GET("receipts/{id}")
    suspend fun getReceipt(@Path("id") id: String): ReceiptDetailResponse

    @PUT("receipts/{id}/confirm")
    suspend fun confirmReceipt(
        @Path("id") id: String,
        @Body body: ReceiptConfirmRequest,
    ): ReceiptDetailResponse

    @DELETE("receipts/{id}")
    suspend fun deleteReceipt(@Path("id") id: String)

    @GET("products/search")
    suspend fun searchProducts(@Query("q") query: String): ProductSearchResponse

    @GET("products/{id}/my-prices")
    suspend fun getProductPrices(@Path("id") id: String): ProductPricesResponse

    @GET("stores")
    suspend fun listStores(): StoreListResponse
}
