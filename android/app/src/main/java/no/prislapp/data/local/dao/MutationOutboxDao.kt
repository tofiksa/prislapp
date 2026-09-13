package no.prislapp.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import no.prislapp.data.local.entity.MutationOutboxEntity

@Dao
interface MutationOutboxDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: MutationOutboxEntity)

    @Query(
        """
        SELECT * FROM mutation_outbox
        WHERE userId = :userId AND status IN ('pending', 'in_flight')
        ORDER BY createdAt ASC
        """,
    )
    suspend fun getSendable(userId: String): List<MutationOutboxEntity>

    @Query("SELECT * FROM mutation_outbox WHERE userId = :userId ORDER BY createdAt ASC")
    suspend fun getAllForUser(userId: String): List<MutationOutboxEntity>

    @Query("SELECT * FROM mutation_outbox WHERE mutationId = :mutationId AND userId = :userId")
    suspend fun getByMutationId(mutationId: String, userId: String): MutationOutboxEntity?

    @Query(
        """
        SELECT * FROM mutation_outbox
        WHERE userId = :userId AND itemId = :itemId AND operation = :operation AND status = 'pending'
        LIMIT 1
        """,
    )
    suspend fun findPendingItemOp(userId: String, itemId: String, operation: String): MutationOutboxEntity?

    @Query("DELETE FROM mutation_outbox WHERE mutationId = :mutationId")
    suspend fun delete(mutationId: String)

    @Query(
        """
        SELECT * FROM mutation_outbox
        WHERE userId = :userId AND status IN ('pending', 'in_flight', 'conflict', 'blocked')
        """,
    )
    suspend fun getProtecting(userId: String): List<MutationOutboxEntity>
}
