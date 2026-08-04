package no.prislapp.data.remote

import no.prislapp.data.remote.dto.GoogleAuthRequest
import no.prislapp.data.remote.dto.LoginRequest
import no.prislapp.data.remote.dto.ReceiptDetailResponse
import no.prislapp.data.remote.dto.ReceiptListResponse
import no.prislapp.data.remote.dto.ReceiptUploadResponse
import no.prislapp.data.remote.dto.RegisterRequest
import no.prislapp.data.remote.dto.TokenResponse
import no.prislapp.data.remote.dto.UserResponse
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
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
    suspend fun listReceipts(@Query("page") page: Int = 1): ReceiptListResponse

    @GET("receipts/{id}")
    suspend fun getReceipt(@Path("id") id: String): ReceiptDetailResponse
}
