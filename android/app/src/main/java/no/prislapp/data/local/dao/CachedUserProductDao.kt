package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.CachedUserProductEntity

@Dao
interface CachedUserProductDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: CachedUserProductEntity)

    @Query("SELECT * FROM cached_user_products WHERE id = :id AND userId = :userId")
    suspend fun get(id: String, userId: String): CachedUserProductEntity?

    @Query(
        """
        SELECT * FROM cached_user_products
        WHERE userId = :userId
        ORDER BY lastPurchasedAt DESC
        """,
    )
    fun observeForUser(userId: String): Flow<List<CachedUserProductEntity>>
}
