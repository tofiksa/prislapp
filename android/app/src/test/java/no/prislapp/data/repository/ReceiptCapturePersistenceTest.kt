package no.prislapp.data.repository

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.work.WorkManager
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import no.prislapp.data.local.PrislappDatabase
import no.prislapp.data.local.TokenStore
import no.prislapp.data.remote.PrislappApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class ReceiptCapturePersistenceTest {
    @Test
    fun queueReceiptCaptureSurvivesDatabaseReopen() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val name = "capture-death-${System.nanoTime()}.db"
        val file = File(context.filesDir, "receipts/receipt_persist.jpg").apply {
            parentFile?.mkdirs()
            writeText("jpeg-bytes")
        }
        val store = mockk<TokenStore>()
        every { store.getUserId() } returns "user-a"
        val workManager = mockk<WorkManager>(relaxed = true)
        val api = mockk<PrislappApi>(relaxed = true)
        var db = openDb(context, name)
        try {
            val id = ReceiptRepository(context, api, db.pendingReceiptDao(), workManager, store)
                .queueReceiptCapture(file)
            val before = db.pendingReceiptDao().getById(id)!!
            assertTrue(File(before.imagePath).exists())
            assertEquals(file.absolutePath, before.imagePath)
            val captureId = before.captureId

            db.close()
            db = openDb(context, name)
            val after = db.pendingReceiptDao().getById(id)!!
            assertEquals(captureId, after.captureId)
            assertEquals(file.absolutePath, after.imagePath)
            assertTrue(File(after.imagePath).exists())
            assertEquals("queued_offline", after.status)
        } finally {
            db.close()
            context.deleteDatabase(name)
            file.delete()
        }
    }

    private fun openDb(context: android.content.Context, name: String) =
        Room.databaseBuilder(context, PrislappDatabase::class.java, name)
            .allowMainThreadQueries()
            .setQueryExecutor { it.run() }
            .setTransactionExecutor { it.run() }
            .build()
}
