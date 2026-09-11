package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "mutation_outbox", indices = [Index("userId")])
data class MutationOutboxEntity(
    @PrimaryKey val mutationId: String,
    val userId: String,
    val operation: String,
    val listId: String? = null,
    val itemId: String? = null,
    val payloadJson: String,
    val status: String = STATUS_PENDING,
    val createdAt: Long = System.currentTimeMillis(),
) {
    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_IN_FLIGHT = "in_flight"
        const val STATUS_CONFLICT = "conflict"
        const val STATUS_BLOCKED = "blocked"
        const val OP_LIST_CREATE = "list_create"
        const val OP_LIST_PATCH = "list_patch"
        const val OP_ITEM_CREATE = "item_create"
        const val OP_ITEM_PATCH = "item_patch"
    }
}
