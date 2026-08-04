package no.prislapp.data.repository

import no.prislapp.data.local.TokenStore
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.GoogleAuthRequest
import no.prislapp.data.remote.dto.LoginRequest
import no.prislapp.data.remote.dto.RegisterRequest
import no.prislapp.domain.model.User
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val api: PrislappApi,
    private val tokenStore: TokenStore,
) {
    val isLoggedIn = tokenStore.isLoggedIn

    suspend fun register(email: String, password: String): Result<User> {
        return authenticate {
            api.register(RegisterRequest(email = email, password = password))
        }
    }

    suspend fun login(email: String, password: String): Result<User> {
        return authenticate {
            api.login(LoginRequest(email = email, password = password))
        }
    }

    suspend fun loginWithGoogle(idToken: String): Result<User> {
        return authenticate {
            api.googleAuth(GoogleAuthRequest(id_token = idToken))
        }
    }

    suspend fun logout() {
        tokenStore.clear()
    }

    private suspend fun authenticate(fetchTokens: suspend () -> no.prislapp.data.remote.dto.TokenResponse): Result<User> {
        return try {
            val tokens = fetchTokens()
            tokenStore.saveTokens(tokens.access_token, tokens.refresh_token)
            val user = api.getMe()
            Result.success(User(id = user.id, email = user.email))
        } catch (exc: HttpException) {
            val message = when (exc.code()) {
                401 -> "Ugyldig e-post eller passord"
                409 -> "E-posten er allerede registrert"
                else -> "Noe gikk galt (${exc.code()})"
            }
            Result.failure(IllegalStateException(message))
        } catch (exc: Exception) {
            Result.failure(IllegalStateException(exc.message ?: "Noe gikk galt"))
        }
    }
}
