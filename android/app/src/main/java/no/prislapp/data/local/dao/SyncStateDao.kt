package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import no.prislapp.data.local.entity.SyncStateEntity

@Dao
interface SyncStateDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: SyncStateEntity)

    @Query("SELECT * FROM sync_state WHERE userId = :userId")
    suspend fun get(userId: String): SyncStateEntity?
}
