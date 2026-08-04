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
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): PrislappDatabase {
        return Room.databaseBuilder(
            context,
            PrislappDatabase::class.java,
            "prislapp.db",
        ).build()
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
