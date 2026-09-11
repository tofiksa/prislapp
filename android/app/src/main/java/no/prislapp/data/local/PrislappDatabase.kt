package no.prislapp.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import no.prislapp.data.local.dao.CachedUserProductDao
import no.prislapp.data.local.dao.MutationOutboxDao
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.dao.PriceSummaryCacheDao
import no.prislapp.data.local.dao.ShoppingListDao
import no.prislapp.data.local.dao.ShoppingListItemDao
import no.prislapp.data.local.dao.SyncConflictDao
import no.prislapp.data.local.dao.SyncStateDao
import no.prislapp.data.local.entity.CachedUserProductEntity
import no.prislapp.data.local.entity.MutationOutboxEntity
import no.prislapp.data.local.entity.PendingReceiptEntity
import no.prislapp.data.local.entity.PriceSummaryCacheEntity
import no.prislapp.data.local.entity.ShoppingListEntity
import no.prislapp.data.local.entity.ShoppingListItemEntity
import no.prislapp.data.local.entity.SyncConflictEntity
import no.prislapp.data.local.entity.SyncStateEntity

@Database(
    entities = [
        PendingReceiptEntity::class,
        ShoppingListEntity::class,
        ShoppingListItemEntity::class,
        MutationOutboxEntity::class,
        SyncConflictEntity::class,
        SyncStateEntity::class,
        CachedUserProductEntity::class,
        PriceSummaryCacheEntity::class,
    ],
    version = 6,
    exportSchema = false,
)
abstract class PrislappDatabase : RoomDatabase() {
    abstract fun pendingReceiptDao(): PendingReceiptDao
    abstract fun shoppingListDao(): ShoppingListDao
    abstract fun shoppingListItemDao(): ShoppingListItemDao
    abstract fun mutationOutboxDao(): MutationOutboxDao
    abstract fun syncConflictDao(): SyncConflictDao
    abstract fun syncStateDao(): SyncStateDao
    abstract fun cachedUserProductDao(): CachedUserProductDao
    abstract fun priceSummaryCacheDao(): PriceSummaryCacheDao
}
