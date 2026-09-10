package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow
import no.prislapp.data.local.entity.PendingReceiptEntity

@Dao
interface PendingReceiptDao {
    @Insert
    suspend fun insert(receipt: PendingReceiptEntity): Long

    @Update
    suspend fun update(receipt: PendingReceiptEntity)

    @Query("SELECT * FROM pending_receipts WHERE userId = :userId AND status != 'CONFIRMED' ORDER BY createdAt DESC")
    fun observeAll(userId: String): Flow<List<PendingReceiptEntity>>

    @Query("SELECT * FROM pending_receipts WHERE id = :id")
    suspend fun getById(id: Long): PendingReceiptEntity?

    @Query(
        """
        SELECT * FROM pending_receipts
        WHERE status IN (:statuses) AND userId = :userId
        ORDER BY createdAt ASC
        """,
    )
    suspend fun getByStatuses(statuses: List<String>, userId: String): List<PendingReceiptEntity>

    @Query("SELECT * FROM pending_receipts WHERE serverReceiptId = :serverReceiptId LIMIT 1")
    suspend fun getByServerReceiptId(serverReceiptId: String): PendingReceiptEntity?

    @Query("DELETE FROM pending_receipts WHERE id = :id")
    suspend fun deleteById(id: Long)

    @Query("SELECT * FROM pending_receipts WHERE createdAt < :before")
    suspend fun getExpired(before: Long): List<PendingReceiptEntity>
}
