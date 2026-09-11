package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "shopping_lists", indices = [Index("userId")])
data class ShoppingListEntity(
    @PrimaryKey val id: String,
    val userId: String,
    val name: String,
    val status: String = STATUS_ACTIVE,
    val version: Int = 1,
    val contentRevision: Int = 0,
    val deleted: Boolean = false,
    val createdAt: String,
    val updatedAt: String,
    val isDraft: Boolean = false,
) {
    companion object {
        const val STATUS_ACTIVE = "active"
        const val STATUS_ARCHIVED = "archived"
    }
}
