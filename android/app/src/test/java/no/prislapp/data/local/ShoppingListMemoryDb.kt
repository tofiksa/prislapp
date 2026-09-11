package no.prislapp.data.local

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map
import no.prislapp.data.local.dao.CachedUserProductDao
import no.prislapp.data.local.dao.MutationOutboxDao
import no.prislapp.data.local.dao.ShoppingListDao
import no.prislapp.data.local.dao.ShoppingListItemDao
import no.prislapp.data.local.dao.SyncConflictDao
import no.prislapp.data.local.dao.SyncStateDao
import no.prislapp.data.local.entity.CachedUserProductEntity
import no.prislapp.data.local.entity.MutationOutboxEntity
import no.prislapp.data.local.entity.ShoppingListEntity
import no.prislapp.data.local.entity.ShoppingListItemEntity
import no.prislapp.data.local.entity.SyncConflictEntity
import no.prislapp.data.local.entity.SyncStateEntity

class ShoppingListMemoryDb {
    val lists = mutableListOf<ShoppingListEntity>()
    val items = mutableListOf<ShoppingListItemEntity>()
    val outbox = mutableListOf<MutationOutboxEntity>()
    val conflicts = mutableListOf<SyncConflictEntity>()
    val syncState = mutableListOf<SyncStateEntity>()
    val products = mutableListOf<CachedUserProductEntity>()
    val listsFlow = MutableStateFlow<List<ShoppingListEntity>>(emptyList())
    val itemsFlow = MutableStateFlow<List<ShoppingListItemEntity>>(emptyList())
    val conflictsFlow = MutableStateFlow<List<SyncConflictEntity>>(emptyList())
    val productsFlow = MutableStateFlow<List<CachedUserProductEntity>>(emptyList())

    fun publish() {
        listsFlow.value = lists.toList()
        itemsFlow.value = items.toList()
        conflictsFlow.value = conflicts.toList()
        productsFlow.value = products.toList()
    }
}

class FakeShoppingListDao(private val db: ShoppingListMemoryDb) : ShoppingListDao {
    override suspend fun upsert(entity: ShoppingListEntity) {
        db.lists.removeAll { it.id == entity.id }
        db.lists.add(entity)
        db.publish()
    }

    override fun observeActive(userId: String): Flow<List<ShoppingListEntity>> =
        db.listsFlow.map { rows -> rows.filter { it.userId == userId && !it.deleted } }

    override suspend fun getAllForUser(userId: String) = db.lists.filter { it.userId == userId }

    override suspend fun get(id: String, userId: String) =
        db.lists.find { it.id == id && it.userId == userId }

    override suspend fun delete(id: String, userId: String) {
        db.lists.removeAll { it.id == id && it.userId == userId }
        db.publish()
    }
}

class FakeShoppingListItemDao(private val db: ShoppingListMemoryDb) : ShoppingListItemDao {
    override suspend fun upsert(entity: ShoppingListItemEntity) {
        db.items.removeAll { it.id == entity.id }
        db.items.add(entity)
        db.publish()
    }

    override fun observeForList(listId: String, userId: String): Flow<List<ShoppingListItemEntity>> =
        db.itemsFlow.map { rows ->
            rows.filter { it.listId == listId && it.userId == userId }.sortedBy { it.position }
        }

    override suspend fun getAllForUser(userId: String) = db.items.filter { it.userId == userId }

    override suspend fun get(id: String, userId: String) =
        db.items.find { it.id == id && it.userId == userId }

    override suspend fun delete(id: String, userId: String) {
        db.items.removeAll { it.id == id && it.userId == userId }
        db.publish()
    }

    override suspend fun maxPosition(listId: String, userId: String) =
        db.items.filter { it.listId == listId && it.userId == userId && !it.deleted }
            .maxOfOrNull { it.position } ?: -1

    override suspend fun findOpenProductLine(
        listId: String,
        userId: String,
        userProductId: String,
        quantityUnit: String,
    ) = db.items
        .filter {
            it.listId == listId && it.userId == userId && it.userProductId == userProductId &&
                it.quantityUnit == quantityUnit && !it.checked && !it.deleted
        }
        .minByOrNull { it.position }
}

open class FakeMutationOutboxDao(private val db: ShoppingListMemoryDb) : MutationOutboxDao {
    override suspend fun upsert(entity: MutationOutboxEntity) {
        db.outbox.removeAll { it.mutationId == entity.mutationId }
        db.outbox.add(entity)
        db.publish()
    }

    override suspend fun getSendable(userId: String) =
        db.outbox.filter {
            it.userId == userId && it.status in setOf(
                MutationOutboxEntity.STATUS_PENDING,
                MutationOutboxEntity.STATUS_IN_FLIGHT,
            )
        }.sortedBy { it.createdAt }

    override suspend fun getAllForUser(userId: String) =
        db.outbox.filter { it.userId == userId }.sortedBy { it.createdAt }

    override suspend fun getByMutationId(mutationId: String, userId: String) =
        db.outbox.find { it.mutationId == mutationId && it.userId == userId }

    override suspend fun findPendingItemOp(userId: String, itemId: String, operation: String) =
        db.outbox.find {
            it.userId == userId && it.itemId == itemId && it.operation == operation &&
                it.status == MutationOutboxEntity.STATUS_PENDING
        }

    override suspend fun delete(mutationId: String) {
        db.outbox.removeAll { it.mutationId == mutationId }
        db.publish()
    }

    override suspend fun getProtecting(userId: String) =
        db.outbox.filter {
            it.userId == userId && it.status in setOf(
                MutationOutboxEntity.STATUS_PENDING,
                MutationOutboxEntity.STATUS_IN_FLIGHT,
                MutationOutboxEntity.STATUS_CONFLICT,
                MutationOutboxEntity.STATUS_BLOCKED,
            )
        }
}

class FakeSyncConflictDao(private val db: ShoppingListMemoryDb) : SyncConflictDao {
    override suspend fun upsert(entity: SyncConflictEntity) {
        db.conflicts.removeAll { it.mutationId == entity.mutationId }
        db.conflicts.add(entity)
        db.publish()
    }

    override fun observe(userId: String): Flow<List<SyncConflictEntity>> =
        db.conflictsFlow.map { rows -> rows.filter { it.userId == userId } }

    override suspend fun getAll(userId: String) = db.conflicts.filter { it.userId == userId }

    override suspend fun get(mutationId: String, userId: String) =
        db.conflicts.find { it.mutationId == mutationId && it.userId == userId }

    override suspend fun delete(mutationId: String) {
        db.conflicts.removeAll { it.mutationId == mutationId }
        db.publish()
    }
}

class FakeSyncStateDao(private val db: ShoppingListMemoryDb) : SyncStateDao {
    override suspend fun upsert(entity: SyncStateEntity) {
        db.syncState.removeAll { it.userId == entity.userId }
        db.syncState.add(entity)
    }

    override suspend fun get(userId: String) = db.syncState.find { it.userId == userId }
}

class FakeCachedUserProductDao(private val db: ShoppingListMemoryDb) : CachedUserProductDao {
    override suspend fun upsert(entity: CachedUserProductEntity) {
        db.products.removeAll { it.id == entity.id }
        db.products.add(entity)
        db.publish()
    }

    override suspend fun get(id: String, userId: String) =
        db.products.find { it.id == id && it.userId == userId }

    override fun observeForUser(userId: String): Flow<List<CachedUserProductEntity>> =
        db.productsFlow.map { rows ->
            rows.filter { it.userId == userId }
                .sortedWith(compareBy<CachedUserProductEntity> { it.lastPurchasedAt == null }
                    .thenByDescending { it.lastPurchasedAt })
        }
}
