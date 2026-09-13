package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "cached_user_products", indices = [Index("userId")])
data class CachedUserProductEntity(
    @PrimaryKey val id: String,
    val userId: String,
    val displayName: String,
    val packContent: String? = null,
    val packUnit: String = "unknown",
    val lastPurchasedAt: String? = null,
)
