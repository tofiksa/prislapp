package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.SyncConflictEntity

@Dao
interface SyncConflictDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: SyncConflictEntity)

    @Query("SELECT * FROM sync_conflicts WHERE userId = :userId")
    fun observe(userId: String): Flow<List<SyncConflictEntity>>

    @Query("SELECT * FROM sync_conflicts WHERE userId = :userId")
    suspend fun getAll(userId: String): List<SyncConflictEntity>

    @Query("SELECT * FROM sync_conflicts WHERE mutationId = :mutationId AND userId = :userId")
    suspend fun get(mutationId: String, userId: String): SyncConflictEntity?

    @Query("DELETE FROM sync_conflicts WHERE mutationId = :mutationId")
    suspend fun delete(mutationId: String)
}
