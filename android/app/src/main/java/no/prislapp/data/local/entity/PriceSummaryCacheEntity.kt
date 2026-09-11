package no.prislapp.data.local.entity

import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "price_summary_cache",
    primaryKeys = ["listId", "userId"],
    indices = [Index("userId")],
)
data class PriceSummaryCacheEntity(
    val listId: String,
    val userId: String,
    val payloadJson: String,
    val listVersion: Int,
    val contentRevision: Int,
    val priceDataVersion: Int,
    val calculatedAt: String,
    val fetchedAt: String,
)
