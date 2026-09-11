package no.prislapp.data.local

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import no.prislapp.data.local.entity.PendingReceiptEntity
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class QueueDatabaseTest {
    @Test fun legacyQueueMigrationKeepsUnattributedCapturesHidden() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "migration-test-${System.nanoTime()}.db"
        context.openOrCreateDatabase(name, 0, null).use { old ->
            old.execSQL("CREATE TABLE pending_receipts (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, imagePath TEXT NOT NULL, serverReceiptId TEXT, status TEXT NOT NULL, createdAt INTEGER NOT NULL)")
            old.execSQL("INSERT INTO pending_receipts(imagePath,status,createdAt) VALUES('/old.jpg','PENDING',1)")
            old.version = 1
        }
        val db = Room.databaseBuilder(context, PrislappDatabase::class.java, name)
            .addMigrations(
                no.prislapp.di.DatabaseModule.MIGRATION_1_2,
                no.prislapp.di.DatabaseModule.MIGRATION_2_3,
            ).build()
        try {
            assertTrue(db.pendingReceiptDao().observeAll("new-user").first().isEmpty())
            assertEquals("/old.jpg", db.pendingReceiptDao().getById(1)?.imagePath)
        } finally { db.close(); context.deleteDatabase(name) }
    }

    @Test fun shoppingListMigrationKeepsPendingReceipts() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "migration-2-3-${System.nanoTime()}.db"
        context.openOrCreateDatabase(name, 0, null).use { old ->
            old.execSQL("CREATE TABLE pending_receipts (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, imagePath TEXT NOT NULL, serverReceiptId TEXT, status TEXT NOT NULL, createdAt INTEGER NOT NULL, userId TEXT NOT NULL, captureId TEXT NOT NULL)")
            old.execSQL("INSERT INTO pending_receipts(imagePath,status,createdAt,userId,captureId) VALUES('/keep.jpg','PENDING',1,'a','cap-1')")
            old.version = 2
        }
        val db = Room.databaseBuilder(context, PrislappDatabase::class.java, name)
            .addMigrations(no.prislapp.di.DatabaseModule.MIGRATION_2_3).build()
        try {
            assertEquals("/keep.jpg", db.pendingReceiptDao().getById(1)?.imagePath)
            assertEquals("a", db.pendingReceiptDao().getById(1)?.userId)
            assertTrue(db.shoppingListDao().getAllForUser("a").isEmpty())
        } finally { db.close(); context.deleteDatabase(name) }
    }

    @Test fun queuesAreIsolatedAndSurviveDatabaseReopen() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "queue-test-${System.nanoTime()}.db"
        var db = Room.databaseBuilder(context, PrislappDatabase::class.java, name).build()
        try {
            val first = PendingReceiptEntity(imagePath = "/a.jpg", userId = "a")
            db.pendingReceiptDao().insert(first)
            db.pendingReceiptDao().insert(PendingReceiptEntity(imagePath = "/b.jpg", userId = "b"))
            db.close()
            db = Room.databaseBuilder(context, PrislappDatabase::class.java, name).build()
            assertEquals(listOf(first.captureId), db.pendingReceiptDao().observeAll("a").first().map { it.captureId })
            assertEquals(1, db.pendingReceiptDao().getByStatuses(listOf("PENDING"), "b").size)
            assertTrue(db.pendingReceiptDao().observeAll("c").first().isEmpty())
        } finally { db.close(); context.deleteDatabase(name) }
    }
}
