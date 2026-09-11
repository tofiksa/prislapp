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
import no.prislapp.data.remote.dto.ShoppingListCollectionDto
import no.prislapp.data.remote.dto.ShoppingListCreateRequest
import no.prislapp.data.remote.dto.ShoppingListDto
import no.prislapp.data.remote.dto.ShoppingListItemDto
import no.prislapp.data.remote.dto.ShoppingListItemPatchRequest
import no.prislapp.data.remote.dto.ShoppingListItemUpsertRequest
import no.prislapp.data.remote.dto.ShoppingListPatchRequest
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryDto
import no.prislapp.data.remote.dto.StoreListResponse
import no.prislapp.data.remote.dto.SyncRequestDto
import no.prislapp.data.remote.dto.SyncResponseDto
import no.prislapp.data.remote.dto.TokenResponse
import no.prislapp.data.remote.dto.UserProductListResponse
import no.prislapp.data.remote.dto.UserResponse
import retrofit2.http.PATCH
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

interface PrislappApi {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("auth/google")
    suspend fun googleAuth(@Body body: GoogleAuthRequest): TokenResponse

    @GET("auth/me")
    suspend fun getMe(@Header("Authorization") authorization: String? = null): UserResponse

    @Multipart
    @POST("receipts")
    suspend fun uploadReceipt(
        @Part file: MultipartBody.Part,
        @Header("Idempotency-Key") captureId: String,
        @Header("X-Local-User") userId: String,
    ): ReceiptUploadResponse

    @POST("receipts/{id}/retry")
    suspend fun retryReceipt(@Path("id") id: String): ReceiptUploadResponse

    @GET("receipts")
    suspend fun listReceipts(
        @Query("page") page: Int = 1,
        @Query("store_id") storeId: String? = null,
        @Query("status") status: String? = null,
        @Query("from_date") fromDate: String? = null,
        @Query("to_date") toDate: String? = null,
    ): ReceiptListResponse

    @GET("receipts/{id}")
    suspend fun getReceipt(@Path("id") id: String): ReceiptDetailResponse

    @GET("receipts/{id}/image")
    @Streaming
    suspend fun getReceiptImage(@Path("id") id: String): ResponseBody

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

    @GET("v2/me/products")
    suspend fun listMyProducts(
        @Query("q") query: String? = null,
        @Query("sort") sort: String = "recent",
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int? = null,
    ): UserProductListResponse

    @GET("v2/shopping-lists")
    suspend fun listShoppingLists(
        @Query("cursor") cursor: String? = null,
        @Query("limit") limit: Int = 50,
        @Header("X-Local-User") userId: String,
    ): ShoppingListCollectionDto

    @POST("v2/shopping-lists")
    suspend fun createShoppingList(
        @Body body: ShoppingListCreateRequest,
        @Header("X-Local-User") userId: String,
    ): ShoppingListDto

    @GET("v2/shopping-lists/{id}")
    suspend fun getShoppingList(
        @Path("id") id: String,
        @Header("X-Local-User") userId: String,
    ): ShoppingListDto

    @GET("v2/shopping-lists/{id}/price-summary")
    suspend fun getShoppingListPriceSummary(
        @Path("id") id: String,
        @Query("include_conditional") includeConditional: Boolean = false,
        @Header("X-Local-User") userId: String,
    ): ShoppingListPriceSummaryDto

    @PATCH("v2/shopping-lists/{id}")
    suspend fun patchShoppingList(
        @Path("id") id: String,
        @Body body: ShoppingListPatchRequest,
        @Header("X-Local-User") userId: String,
    ): ShoppingListDto

    @POST("v2/shopping-lists/{id}/items")
    suspend fun addShoppingListItem(
        @Path("id") id: String,
        @Body body: ShoppingListItemUpsertRequest,
        @Header("X-Local-User") userId: String,
    ): ShoppingListItemDto

    @PATCH("v2/shopping-lists/{id}/items/{item_id}")
    suspend fun patchShoppingListItem(
        @Path("id") id: String,
        @Path("item_id") itemId: String,
        @Body body: ShoppingListItemPatchRequest,
        @Header("X-Local-User") userId: String,
    ): ShoppingListItemDto

    @POST("v2/sync")
    suspend fun syncShoppingLists(
        @Body body: SyncRequestDto,
        @Header("X-Local-User") userId: String,
    ): SyncResponseDto
}
