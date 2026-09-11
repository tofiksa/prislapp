package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.PriceSummaryCacheEntity

@Dao
interface PriceSummaryCacheDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: PriceSummaryCacheEntity)

    @Query("SELECT * FROM price_summary_cache WHERE listId = :listId AND userId = :userId")
    suspend fun get(listId: String, userId: String): PriceSummaryCacheEntity?

    @Query("SELECT * FROM price_summary_cache WHERE listId = :listId AND userId = :userId")
    fun observe(listId: String, userId: String): Flow<PriceSummaryCacheEntity?>
}
