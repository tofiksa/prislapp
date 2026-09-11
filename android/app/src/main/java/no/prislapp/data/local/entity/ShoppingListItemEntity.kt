package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "shopping_list_items",
    indices = [Index("userId"), Index("listId")],
)
data class ShoppingListItemEntity(
    @PrimaryKey val id: String,
    val listId: String,
    val userId: String,
    val userProductId: String? = null,
    val freeText: String? = null,
    val quantity: String,
    val quantityUnit: String,
    val checked: Boolean = false,
    val position: Int = 0,
    val version: Int = 1,
    val deleted: Boolean = false,
)
