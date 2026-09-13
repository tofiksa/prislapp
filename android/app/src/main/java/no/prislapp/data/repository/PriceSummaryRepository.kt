package no.prislapp.data.repository

import com.google.gson.Gson
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import no.prislapp.data.local.AccountSession
import no.prislapp.data.local.dao.PriceSummaryCacheDao
import no.prislapp.data.local.entity.PriceSummaryCacheEntity
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ShoppingListPriceSummaryDto
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

data class CachedPriceSummary(
    val summary: ShoppingListPriceSummaryDto,
    val fetchedAt: String,
)

@Singleton
class PriceSummaryRepository @Inject constructor(
    private val api: PrislappApi,
    private val cacheDao: PriceSummaryCacheDao,
    private val accountSession: AccountSession,
) {
    private val gson = Gson()

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeCached(listId: String): Flow<CachedPriceSummary?> =
        accountSession.observeUserId().flatMapLatest { userId ->
            if (userId == null) {
                flowOf(null)
            } else {
                cacheDao.observe(listId, userId).map { it?.toCached() }
            }
        }

    suspend fun cached(listId: String): CachedPriceSummary? {
        val userId = accountSession.currentUserId() ?: return null
        return cacheDao.get(listId, userId)?.toCached()
    }

    suspend fun refresh(listId: String): ShoppingListPriceSummaryDto {
        val userId = checkNotNull(accountSession.currentUserId()) { "Logg inn først" }
        val summary = api.getShoppingListPriceSummary(
            id = listId,
            includeConditional = false,
            userId = userId,
        )
        val existing = cacheDao.get(listId, userId)
        val incomingAt = runCatching { Instant.parse(summary.calculated_at) }.getOrNull()
        val existingAt = existing?.let { runCatching { Instant.parse(it.calculatedAt) }.getOrNull() }
        val staleCache = existing != null && (
            summary.content_revision < existing.contentRevision ||
                (incomingAt != null && existingAt != null && incomingAt.isBefore(existingAt))
            )
        if (!staleCache) {
            cacheDao.upsert(
                PriceSummaryCacheEntity(
                    listId = listId,
                    userId = userId,
                    payloadJson = gson.toJson(summary),
                    listVersion = summary.list_version,
                    contentRevision = summary.content_revision,
                    priceDataVersion = summary.price_data_version,
                    calculatedAt = summary.calculated_at,
                    fetchedAt = Instant.now().toString(),
                ),
            )
        }
        return summary
    }

    private fun PriceSummaryCacheEntity.toCached() = CachedPriceSummary(
        summary = gson.fromJson(payloadJson, ShoppingListPriceSummaryDto::class.java),
        fetchedAt = fetchedAt,
    )
}
