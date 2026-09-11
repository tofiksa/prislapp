package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.ShoppingListItemEntity

@Dao
interface ShoppingListItemDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: ShoppingListItemEntity)

    @Query("SELECT * FROM shopping_list_items WHERE listId = :listId AND userId = :userId ORDER BY position ASC")
    fun observeForList(listId: String, userId: String): Flow<List<ShoppingListItemEntity>>

    @Query("SELECT * FROM shopping_list_items WHERE userId = :userId")
    suspend fun getAllForUser(userId: String): List<ShoppingListItemEntity>

    @Query("SELECT * FROM shopping_list_items WHERE id = :id AND userId = :userId")
    suspend fun get(id: String, userId: String): ShoppingListItemEntity?

    @Query("DELETE FROM shopping_list_items WHERE id = :id AND userId = :userId")
    suspend fun delete(id: String, userId: String)

    @Query("SELECT COALESCE(MAX(position), -1) FROM shopping_list_items WHERE listId = :listId AND userId = :userId AND deleted = 0")
    suspend fun maxPosition(listId: String, userId: String): Int
}
