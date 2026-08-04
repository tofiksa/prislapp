package no.prislapp.data.remote.dto

data class RegisterRequest(
    val email: String,
    val password: String,
)

data class LoginRequest(
    val email: String,
    val password: String,
)

data class GoogleAuthRequest(
    val id_token: String,
)

data class TokenResponse(
    val access_token: String,
    val refresh_token: String,
    val token_type: String,
)

data class UserResponse(
    val id: String,
    val email: String,
)
