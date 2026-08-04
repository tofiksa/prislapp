package no.prislapp.ui.auth

import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import no.prislapp.BuildConfig
import javax.inject.Inject

class GoogleSignInHelper @Inject constructor() {
    suspend fun getIdToken(context: Context): Result<String> {
        val clientId = BuildConfig.GOOGLE_WEB_CLIENT_ID
        if (clientId.isBlank()) {
            return Result.failure(IllegalStateException("Google Sign-In er ikke konfigurert"))
        }

        return try {
            val googleIdOption = GetGoogleIdOption.Builder()
                .setFilterByAuthorizedAccounts(false)
                .setServerClientId(clientId)
                .build()

            val request = GetCredentialRequest.Builder()
                .addCredentialOption(googleIdOption)
                .build()

            val credentialManager = CredentialManager.create(context)
            val result = credentialManager.getCredential(context, request)
            val googleCredential = GoogleIdTokenCredential.createFrom(result.credential.data)
            Result.success(googleCredential.idToken)
        } catch (exc: GetCredentialException) {
            Result.failure(IllegalStateException("Google-innlogging avbrutt"))
        } catch (exc: Exception) {
            Result.failure(IllegalStateException(exc.message ?: "Google-innlogging feilet"))
        }
    }
}
