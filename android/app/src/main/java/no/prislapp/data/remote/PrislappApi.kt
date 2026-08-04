package no.prislapp.data.remote

import no.prislapp.data.remote.dto.GoogleAuthRequest
import no.prislapp.data.remote.dto.LoginRequest
import no.prislapp.data.remote.dto.RegisterRequest
import no.prislapp.data.remote.dto.TokenResponse
import no.prislapp.data.remote.dto.UserResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface PrislappApi {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("auth/google")
    suspend fun googleAuth(@Body body: GoogleAuthRequest): TokenResponse

    @GET("auth/me")
    suspend fun getMe(): UserResponse
}
