package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.ShoppingListEntity

@Dao
interface ShoppingListDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ShoppingListEntity)

    @Query("SELECT * FROM shopping_lists WHERE userId = :userId AND deleted = 0 ORDER BY createdAt ASC")
    fun observeActive(userId: String): Flow<List<ShoppingListEntity>>

    @Query("SELECT * FROM shopping_lists WHERE userId = :userId")
    suspend fun getAllForUser(userId: String): List<ShoppingListEntity>

    @Query("SELECT * FROM shopping_lists WHERE id = :id AND userId = :userId")
    suspend fun get(id: String, userId: String): ShoppingListEntity?

    @Query("DELETE FROM shopping_lists WHERE id = :id AND userId = :userId")
    suspend fun delete(id: String, userId: String)
}
