package no.prislapp.data.local

import kotlinx.coroutines.flow.Flow

interface AccountSession {
    fun currentUserId(): String?
    fun observeUserId(): Flow<String?>
}

class TokenAccountSession(
    private val tokenStore: TokenStore,
) : AccountSession {
    override fun currentUserId(): String? = tokenStore.getUserId()
    override fun observeUserId(): Flow<String?> = tokenStore.userId
}

fun interface SyncEnqueuer {
    fun enqueueShoppingListSync()
}
