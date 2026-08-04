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

    @Query("SELECT * FROM pending_receipts ORDER BY createdAt DESC")
    fun observeAll(): Flow<List<PendingReceiptEntity>>

    @Query("SELECT * FROM pending_receipts WHERE id = :id")
    suspend fun getById(id: Long): PendingReceiptEntity?

    @Query(
        """
        SELECT * FROM pending_receipts
        WHERE status IN (:statuses)
        ORDER BY createdAt ASC
        """,
    )
    suspend fun getByStatuses(statuses: List<String>): List<PendingReceiptEntity>

    @Query("SELECT * FROM pending_receipts WHERE serverReceiptId = :serverReceiptId LIMIT 1")
    suspend fun getByServerReceiptId(serverReceiptId: String): PendingReceiptEntity?
}
