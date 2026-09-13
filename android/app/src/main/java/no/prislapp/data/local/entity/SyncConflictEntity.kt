package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "sync_conflicts", indices = [Index("userId")])
data class SyncConflictEntity(
    @PrimaryKey val mutationId: String,
    val userId: String,
    val operation: String,
    val code: String,
    val message: String,
    val localJson: String,
    val serverJson: String? = null,
    val listId: String? = null,
    val itemId: String? = null,
)
