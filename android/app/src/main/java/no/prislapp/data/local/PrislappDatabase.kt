package no.prislapp.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.entity.PendingReceiptEntity

@Database(
    entities = [PendingReceiptEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class PrislappDatabase : RoomDatabase() {
    abstract fun pendingReceiptDao(): PendingReceiptDao
}
