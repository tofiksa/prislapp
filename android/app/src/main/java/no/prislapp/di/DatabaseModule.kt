package no.prislapp.di

import android.content.Context
import androidx.room.Room
import androidx.room.withTransaction
import androidx.work.WorkManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import no.prislapp.data.local.AccountSession
import no.prislapp.data.local.PrislappDatabase
import no.prislapp.data.local.SyncEnqueuer
import no.prislapp.data.local.TokenAccountSession
import no.prislapp.data.local.TokenStore
import no.prislapp.data.local.TransactionRunner
import no.prislapp.data.local.dao.CachedUserProductDao
import no.prislapp.data.local.dao.MutationOutboxDao
import no.prislapp.data.local.dao.PendingReceiptDao
import no.prislapp.data.local.dao.ShoppingListDao
import no.prislapp.data.local.dao.ShoppingListItemDao
import no.prislapp.data.local.dao.SyncConflictDao
import no.prislapp.data.local.dao.SyncStateDao
import no.prislapp.worker.ShoppingListSyncWorker
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    val MIGRATION_1_2 = object : androidx.room.migration.Migration(1, 2) {
        override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
            // Legacy captures cannot be safely attributed to the current account.
            db.execSQL("ALTER TABLE pending_receipts ADD COLUMN userId TEXT NOT NULL DEFAULT ''")
            db.execSQL("ALTER TABLE pending_receipts ADD COLUMN captureId TEXT NOT NULL DEFAULT ''")
            db.execSQL("UPDATE pending_receipts SET captureId = lower(hex(randomblob(16)))")
        }
    }

    val MIGRATION_2_3 = object : androidx.room.migration.Migration(2, 3) {
        override fun migrate(db: androidx.sqlite.db.SupportSQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `shopping_lists` (
                    `id` TEXT NOT NULL,
                    `userId` TEXT NOT NULL,
                    `name` TEXT NOT NULL,
                    `status` TEXT NOT NULL,
                    `version` INTEGER NOT NULL,
                    `contentRevision` INTEGER NOT NULL,
                    `deleted` INTEGER NOT NULL,
                    `createdAt` TEXT NOT NULL,
                    `updatedAt` TEXT NOT NULL,
                    `isDraft` INTEGER NOT NULL,
                    PRIMARY KEY(`id`)
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_shopping_lists_userId` ON `shopping_lists` (`userId`)")
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `shopping_list_items` (
                    `id` TEXT NOT NULL,
                    `listId` TEXT NOT NULL,
                    `userId` TEXT NOT NULL,
                    `userProductId` TEXT,
                    `freeText` TEXT,
                    `quantity` TEXT NOT NULL,
                    `quantityUnit` TEXT NOT NULL,
                    `checked` INTEGER NOT NULL,
                    `position` INTEGER NOT NULL,
                    `version` INTEGER NOT NULL,
                    `deleted` INTEGER NOT NULL,
                    PRIMARY KEY(`id`)
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_shopping_list_items_userId` ON `shopping_list_items` (`userId`)")
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_shopping_list_items_listId` ON `shopping_list_items` (`listId`)")
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `mutation_outbox` (
                    `mutationId` TEXT NOT NULL,
                    `userId` TEXT NOT NULL,
                    `operation` TEXT NOT NULL,
                    `listId` TEXT,
                    `itemId` TEXT,
                    `payloadJson` TEXT NOT NULL,
                    `status` TEXT NOT NULL,
                    `createdAt` INTEGER NOT NULL,
                    PRIMARY KEY(`mutationId`)
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_mutation_outbox_userId` ON `mutation_outbox` (`userId`)")
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `sync_conflicts` (
                    `mutationId` TEXT NOT NULL,
                    `userId` TEXT NOT NULL,
                    `operation` TEXT NOT NULL,
                    `code` TEXT NOT NULL,
                    `message` TEXT NOT NULL,
                    `localJson` TEXT NOT NULL,
                    `serverJson` TEXT,
                    `listId` TEXT,
                    `itemId` TEXT,
                    PRIMARY KEY(`mutationId`)
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_sync_conflicts_userId` ON `sync_conflicts` (`userId`)")
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `sync_state` (
                    `userId` TEXT NOT NULL,
                    `cursor` TEXT,
                    PRIMARY KEY(`userId`)
                )
                """.trimIndent(),
            )
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS `cached_user_products` (
                    `id` TEXT NOT NULL,
                    `userId` TEXT NOT NULL,
                    `displayName` TEXT NOT NULL,
                    PRIMARY KEY(`id`)
                )
                """.trimIndent(),
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS `index_cached_user_products_userId` ON `cached_user_products` (`userId`)")
        }
    }

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): PrislappDatabase {
        return Room.databaseBuilder(
            context,
            PrislappDatabase::class.java,
            "prislapp.db",
        ).addMigrations(MIGRATION_1_2, MIGRATION_2_3).build()
    }

    @Provides
    fun providePendingReceiptDao(database: PrislappDatabase): PendingReceiptDao {
        return database.pendingReceiptDao()
    }

    @Provides
    fun provideShoppingListDao(database: PrislappDatabase): ShoppingListDao = database.shoppingListDao()

    @Provides
    fun provideShoppingListItemDao(database: PrislappDatabase): ShoppingListItemDao =
        database.shoppingListItemDao()

    @Provides
    fun provideMutationOutboxDao(database: PrislappDatabase): MutationOutboxDao =
        database.mutationOutboxDao()

    @Provides
    fun provideSyncConflictDao(database: PrislappDatabase): SyncConflictDao = database.syncConflictDao()

    @Provides
    fun provideSyncStateDao(database: PrislappDatabase): SyncStateDao = database.syncStateDao()

    @Provides
    fun provideCachedUserProductDao(database: PrislappDatabase): CachedUserProductDao =
        database.cachedUserProductDao()

    @Provides
    fun provideTransactionRunner(database: PrislappDatabase): TransactionRunner {
        return object : TransactionRunner {
            override suspend fun <T> run(block: suspend () -> T): T = database.withTransaction(block)
        }
    }

    @Provides
    fun provideAccountSession(tokenStore: TokenStore): AccountSession = TokenAccountSession(tokenStore)

    @Provides
    fun provideShoppingListSyncEnqueuer(workManager: WorkManager): SyncEnqueuer =
        SyncEnqueuer { ShoppingListSyncWorker.enqueue(workManager) }

    @Provides
    @Singleton
    fun provideWorkManager(@ApplicationContext context: Context): WorkManager {
        return WorkManager.getInstance(context)
    }
}
