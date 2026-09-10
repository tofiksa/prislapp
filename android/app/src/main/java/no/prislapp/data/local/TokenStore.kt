package no.prislapp.data.local

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking
import javax.inject.Inject
import javax.inject.Singleton
import android.util.Base64
import org.json.JSONObject

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "auth_tokens")

@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val accessTokenKey = stringPreferencesKey("access_token")
    private val refreshTokenKey = stringPreferencesKey("refresh_token")

    @Volatile
    private var cachedAccessToken: String? = null
    @Volatile private var cachedRefreshToken: String? = null

    fun getRefreshToken(): String? = cachedRefreshToken

    fun getUserId(): String? = userIdFromToken(cachedAccessToken)

    private fun userIdFromToken(token: String?): String? = try {
        token?.split('.')?.getOrNull(1)?.let {
            JSONObject(String(Base64.decode(it, Base64.URL_SAFE or Base64.NO_WRAP))).getString("sub")
        }
    } catch (_: Exception) { null }

    init {
        cachedAccessToken = runBlocking {
            val prefs = context.dataStore.data.first()
            cachedRefreshToken = prefs[refreshTokenKey]
            prefs[accessTokenKey]
        }
    }

    val isLoggedIn: Flow<Boolean> = context.dataStore.data.map { prefs ->
        !prefs[accessTokenKey].isNullOrBlank()
    }
    val userId: Flow<String?> = context.dataStore.data.map { userIdFromToken(it[accessTokenKey]) }

    fun getAccessToken(): String? = cachedAccessToken

    suspend fun saveTokens(accessToken: String, refreshToken: String) {
        cachedAccessToken = accessToken
        cachedRefreshToken = refreshToken
        context.dataStore.edit { prefs ->
            prefs[accessTokenKey] = accessToken
            prefs[refreshTokenKey] = refreshToken
        }
    }

    suspend fun clear() {
        cachedAccessToken = null
        cachedRefreshToken = null
        context.dataStore.edit { prefs ->
            prefs.remove(accessTokenKey)
            prefs.remove(refreshTokenKey)
        }
    }
}
