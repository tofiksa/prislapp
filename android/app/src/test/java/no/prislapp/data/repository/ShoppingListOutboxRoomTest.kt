package no.prislapp.data.repository

import androidx.room.Room
import androidx.room.withTransaction
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.runBlocking
import no.prislapp.data.local.AccountSession
import no.prislapp.data.local.PrislappDatabase
import no.prislapp.data.local.SyncEnqueuer
import no.prislapp.data.local.TransactionRunner
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.SyncRequestDto
import no.prislapp.data.remote.dto.SyncResponseDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ShoppingListOutboxRoomTest {
    @Test
    fun twentyOfflineMutationsSurviveProcessDeathAndEachMutationIdIsSentOnce() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "outbox-death-${System.nanoTime()}.db"
        val userId = "user-a"
        val api = mockk<PrislappApi>(relaxed = true)
        var db = openDb(context, name)
        try {
            repository(db, api, userId).let { first ->
                val listId = first.createList("Ukeshandel")
                repeat(19) { first.addItem(listId, freeText = "Vare $it") }
            }
            assertEquals(20, db.mutationOutboxDao().getSendable(userId).size)

            db.close()
            db = openDb(context, name)
            assertEquals(20, db.mutationOutboxDao().getSendable(userId).size)

            val sentIds = mutableListOf<String>()
            coEvery { api.syncShoppingLists(any(), any()) } answers {
                sentIds += firstArg<SyncRequestDto>().mutations.map { it.mutation_id }
                SyncResponseDto(cursor = "cursor-1", price_data_version = 1, full_snapshot = false)
            }

            val afterDeath = repository(db, api, userId)
            afterDeath.syncPending()
            afterDeath.syncPending()

            assertEquals(20, sentIds.size)
            assertEquals(sentIds.toSet().size, sentIds.size)
            assertTrue(afterDeath.pendingMutations().isEmpty())
        } finally {
            db.close()
            context.deleteDatabase(name)
        }
    }

    private fun openDb(context: android.content.Context, name: String) =
        Room.databaseBuilder(context, PrislappDatabase::class.java, name)
            .allowMainThreadQueries()
            .setQueryExecutor { it.run() }
            .setTransactionExecutor { it.run() }
            .build()

    private fun repository(
        db: PrislappDatabase,
        api: PrislappApi,
        userId: String,
    ): ShoppingListRepository {
        val sessionUser = MutableStateFlow<String?>(userId)
        return ShoppingListRepository(
            api = api,
            listDao = db.shoppingListDao(),
            itemDao = db.shoppingListItemDao(),
            outboxDao = db.mutationOutboxDao(),
            conflictDao = db.syncConflictDao(),
            syncStateDao = db.syncStateDao(),
            productCacheDao = db.cachedUserProductDao(),
            accountSession = object : AccountSession {
                override fun currentUserId() = sessionUser.value
                override fun observeUserId() = sessionUser
            },
            syncEnqueuer = SyncEnqueuer { },
            transactionRunner = object : TransactionRunner {
                override suspend fun <T> run(block: suspend () -> T): T = db.withTransaction(block)
            },
        )
    }
}
