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

    @Test
    fun migration3To4KeepsReceiptsListsAndAddsPackColumns() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "migration-3-4-${System.nanoTime()}.db"
        context.openOrCreateDatabase(name, 0, null).use { old ->
            old.execSQL(
                "CREATE TABLE pending_receipts (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, imagePath TEXT NOT NULL, serverReceiptId TEXT, status TEXT NOT NULL, createdAt INTEGER NOT NULL, userId TEXT NOT NULL, captureId TEXT NOT NULL)",
            )
            old.execSQL("INSERT INTO pending_receipts(imagePath,status,createdAt,userId,captureId) VALUES('/keep.jpg','PENDING',1,'a','cap-1')")
            old.execSQL(
                "CREATE TABLE shopping_lists (id TEXT NOT NULL, userId TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL, contentRevision INTEGER NOT NULL, deleted INTEGER NOT NULL, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, isDraft INTEGER NOT NULL, PRIMARY KEY(id))",
            )
            old.execSQL("INSERT INTO shopping_lists VALUES('l1','a','Tur','active',1,0,0,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',0)")
            old.execSQL("CREATE INDEX IF NOT EXISTS index_shopping_lists_userId ON shopping_lists (userId)")
            old.execSQL(
                "CREATE TABLE shopping_list_items (id TEXT NOT NULL, listId TEXT NOT NULL, userId TEXT NOT NULL, userProductId TEXT, freeText TEXT, quantity TEXT NOT NULL, quantityUnit TEXT NOT NULL, checked INTEGER NOT NULL, position INTEGER NOT NULL, version INTEGER NOT NULL, deleted INTEGER NOT NULL, PRIMARY KEY(id))",
            )
            old.execSQL("CREATE INDEX IF NOT EXISTS index_shopping_list_items_userId ON shopping_list_items (userId)")
            old.execSQL("CREATE INDEX IF NOT EXISTS index_shopping_list_items_listId ON shopping_list_items (listId)")
            old.execSQL(
                "CREATE TABLE mutation_outbox (mutationId TEXT NOT NULL, userId TEXT NOT NULL, operation TEXT NOT NULL, listId TEXT, itemId TEXT, payloadJson TEXT NOT NULL, status TEXT NOT NULL, createdAt INTEGER NOT NULL, PRIMARY KEY(mutationId))",
            )
            old.execSQL("CREATE INDEX IF NOT EXISTS index_mutation_outbox_userId ON mutation_outbox (userId)")
            old.execSQL(
                "CREATE TABLE sync_conflicts (mutationId TEXT NOT NULL, userId TEXT NOT NULL, operation TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL, localJson TEXT NOT NULL, serverJson TEXT, listId TEXT, itemId TEXT, PRIMARY KEY(mutationId))",
            )
            old.execSQL("CREATE INDEX IF NOT EXISTS index_sync_conflicts_userId ON sync_conflicts (userId)")
            old.execSQL("CREATE TABLE sync_state (userId TEXT NOT NULL, cursor TEXT, PRIMARY KEY(userId))")
            old.execSQL(
                "CREATE TABLE cached_user_products (id TEXT NOT NULL, userId TEXT NOT NULL, displayName TEXT NOT NULL, PRIMARY KEY(id))",
            )
            old.execSQL("CREATE INDEX IF NOT EXISTS index_cached_user_products_userId ON cached_user_products (userId)")
            old.execSQL("INSERT INTO cached_user_products VALUES('p1','a','Melk')")
            old.version = 3
        }
        val db = Room.databaseBuilder(context, PrislappDatabase::class.java, name)
            .addMigrations(
                no.prislapp.di.DatabaseModule.MIGRATION_3_4,
                no.prislapp.di.DatabaseModule.MIGRATION_4_5,
                no.prislapp.di.DatabaseModule.MIGRATION_5_6,
            )
            .allowMainThreadQueries()
            .build()
        try {
            assertEquals("/keep.jpg", db.pendingReceiptDao().getById(1)?.imagePath)
            assertEquals("queued_offline", db.pendingReceiptDao().getById(1)?.status)
            assertEquals(null, db.pendingReceiptDao().getById(1)?.lastErrorCode)
            assertEquals("Tur", db.shoppingListDao().get("l1", "a")?.name)
            val cached = db.cachedUserProductDao().get("p1", "a")
            assertEquals("Melk", cached?.displayName)
            assertEquals("unknown", cached?.packUnit)
            assertEquals(null, cached?.packContent)
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
