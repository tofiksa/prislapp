package no.prislapp.data.remote

import no.prislapp.data.local.TokenStore
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import java.io.IOException
import kotlinx.coroutines.runBlocking
import com.google.gson.Gson
import no.prislapp.data.remote.dto.TokenResponse
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
) : Interceptor {
    private val publicPaths = setOf("auth/register", "auth/login", "auth/google", "auth/refresh")
    private val refreshLock = Any()

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val path = request.url.encodedPath.trimStart('/')

        if (publicPaths.any { path.endsWith(it) }) {
            return chain.proceed(request)
        }
        if (request.header("Authorization") != null && path == "auth/me") return chain.proceed(request)

        val token = tokenStore.getAccessToken()
        val owner = request.header("X-Local-User") ?: tokenStore.getUserId()
        if (owner != null && owner != tokenStore.getUserId()) throw IOException("Kontoen er endret")
        val authenticatedRequest = if (token != null) {
            request.newBuilder()
                .removeHeader("X-Local-User")
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            request.newBuilder().removeHeader("X-Local-User").build()
        }

        val response = chain.proceed(authenticatedRequest)
        if (response.code != 401 || token == null) return response
        synchronized(refreshLock) {
            if (owner != tokenStore.getUserId()) return response
            if (tokenStore.getAccessToken() == token) {
                val refresh = tokenStore.getRefreshToken() ?: return response
                val url = request.url.newBuilder().encodedPath("/auth/refresh").query(null).build()
                val body = Gson().toJson(mapOf("refresh_token" to refresh))
                    .toRequestBody("application/json".toMediaType())
                val refreshRequest = okhttp3.Request.Builder().url(url).post(body).build()
                // Release the original response before issuing another request on this chain.
                val buffered = response.newBuilder().body(response.peekBody(1024 * 1024)).build()
                response.close()
                try {
                    chain.proceed(refreshRequest).use { renewed ->
                        if (owner != tokenStore.getUserId() || tokenStore.getAccessToken() != token) return buffered
                        if (!renewed.isSuccessful) {
                            if (renewed.code == 401) runBlocking { tokenStore.clear() }
                            return buffered
                        }
                        val tokens = Gson().fromJson(renewed.body!!.string(), TokenResponse::class.java)
                        runBlocking { tokenStore.saveTokens(tokens.access_token, tokens.refresh_token) }
                    }
                } catch (_: Exception) { return buffered }
            }
            if (owner != tokenStore.getUserId()) return response
            val fresh = tokenStore.getAccessToken() ?: return response
            response.close()
            return chain.proceed(authenticatedRequest.newBuilder().header("Authorization", "Bearer $fresh").build())
        }
    }
}
