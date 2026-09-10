package no.prislapp.di

import android.content.Context
import androidx.room.Room
import androidx.work.WorkManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import no.prislapp.data.local.PrislappDatabase
import no.prislapp.data.local.dao.PendingReceiptDao
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
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): PrislappDatabase {
        return Room.databaseBuilder(
            context,
            PrislappDatabase::class.java,
            "prislapp.db",
        ).addMigrations(MIGRATION_1_2).build()
    }

    @Provides
    fun providePendingReceiptDao(database: PrislappDatabase): PendingReceiptDao {
        return database.pendingReceiptDao()
    }

    @Provides
    @Singleton
    fun provideWorkManager(@ApplicationContext context: Context): WorkManager {
        return WorkManager.getInstance(context)
    }
}
