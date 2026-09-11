package no.prislapp.data.repository

import com.google.gson.Gson
import com.google.gson.JsonParser
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import no.prislapp.data.local.AccountSession
import no.prislapp.data.local.SyncEnqueuer
import no.prislapp.data.local.TransactionRunner
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
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ShoppingListDto
import no.prislapp.data.remote.dto.ShoppingListItemDto
import no.prislapp.data.remote.dto.SyncMutationDto
import no.prislapp.data.remote.dto.SyncRequestDto
import no.prislapp.data.remote.dto.SyncResponseDto
import no.prislapp.domain.QuantityFormat
import java.math.BigDecimal
import java.time.Instant
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ShoppingListRepository @Inject constructor(
    private val api: PrislappApi,
    private val listDao: ShoppingListDao,
    private val itemDao: ShoppingListItemDao,
    private val outboxDao: MutationOutboxDao,
    private val conflictDao: SyncConflictDao,
    private val syncStateDao: SyncStateDao,
    private val productCacheDao: CachedUserProductDao,
    private val accountSession: AccountSession,
    private val syncEnqueuer: SyncEnqueuer,
    private val transactionRunner: TransactionRunner,
) {
    private val gson = Gson()

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeLists(): Flow<List<ShoppingListEntity>> =
        accountSession.observeUserId().flatMapLatest { user ->
            if (user == null) flowOf(emptyList()) else listDao.observeActive(user)
        }

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeItems(listId: String): Flow<List<ShoppingListItemEntity>> =
        accountSession.observeUserId().flatMapLatest { user ->
            if (user == null) flowOf(emptyList()) else itemDao.observeForList(listId, user)
        }

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeConflicts(): Flow<List<SyncConflictEntity>> =
        accountSession.observeUserId().flatMapLatest { user ->
            if (user == null) flowOf(emptyList()) else conflictDao.observe(user)
        }

    suspend fun createList(name: String): String {
        val userId = requireUser()
        val id = UUID.randomUUID().toString()
        val now = Instant.now().toString()
        val mutation = SyncMutationDto(
            operation = MutationOutboxEntity.OP_LIST_CREATE,
            mutation_id = UUID.randomUUID().toString(),
            id = id,
            name = name,
        )
        transactionRunner.run {
            listDao.upsert(
                ShoppingListEntity(
                    id = id,
                    userId = userId,
                    name = name,
                    createdAt = now,
                    updatedAt = now,
                ),
            )
            outboxDao.upsert(toOutbox(mutation, userId, listId = id))
        }
        enqueueSync()
        return id
    }

    suspend fun addItem(
        listId: String,
        freeText: String? = null,
        userProductId: String? = null,
        productDisplayName: String? = null,
        quantity: BigDecimal = BigDecimal.ONE,
        quantityUnit: String = "each",
    ): String {
        val userId = requireUser()
        require((freeText == null) xor (userProductId == null)) {
            "Oppgi enten fritekst eller produkt, ikke begge"
        }
        val itemId = UUID.randomUUID().toString()
        val qty = QuantityFormat.toJson(quantity)
        transactionRunner.run {
            val position = itemDao.maxPosition(listId, userId) + 1
            itemDao.upsert(
                ShoppingListItemEntity(
                    id = itemId,
                    listId = listId,
                    userId = userId,
                    userProductId = userProductId,
                    freeText = freeText,
                    quantity = qty,
                    quantityUnit = quantityUnit,
                    position = position,
                ),
            )
            if (userProductId != null && productDisplayName != null) {
                productCacheDao.upsert(
                    CachedUserProductEntity(id = userProductId, userId = userId, displayName = productDisplayName),
                )
            }
            outboxDao.upsert(
                toOutbox(
                    SyncMutationDto(
                        operation = MutationOutboxEntity.OP_ITEM_CREATE,
                        mutation_id = UUID.randomUUID().toString(),
                        list_id = listId,
                        id = itemId,
                        user_product_id = userProductId,
                        free_text = freeText,
                        quantity = qty,
                        quantity_unit = quantityUnit,
                        checked = false,
                        position = position,
                    ),
                    userId,
                    listId = listId,
                    itemId = itemId,
                ),
            )
        }
        enqueueSync()
        return itemId
    }

    suspend fun setItemQuantity(listId: String, itemId: String, quantity: BigDecimal) {
        val formatted = QuantityFormat.toJson(quantity)
        patchItem(listId, itemId, { it.copy(quantity = formatted) }) { current, mutationId ->
            SyncMutationDto(
                operation = MutationOutboxEntity.OP_ITEM_PATCH,
                mutation_id = mutationId,
                list_id = listId,
                item_id = itemId,
                expected_version = current.version,
                quantity = formatted,
            )
        }
    }

    suspend fun setItemChecked(listId: String, itemId: String, checked: Boolean) {
        patchItem(listId, itemId, { it.copy(checked = checked) }) { current, mutationId ->
            SyncMutationDto(
                operation = MutationOutboxEntity.OP_ITEM_PATCH,
                mutation_id = mutationId,
                list_id = listId,
                item_id = itemId,
                expected_version = current.version,
                checked = checked,
            )
        }
    }

    suspend fun getItem(itemId: String): ShoppingListItemEntity? {
        val userId = accountSession.currentUserId() ?: return null
        return itemDao.get(itemId, userId)
    }

    suspend fun pendingMutations(): List<String> {
        val userId = accountSession.currentUserId() ?: return emptyList()
        return outboxDao.getAllForUser(userId).map { it.mutationId }
    }

    suspend fun syncPending() {
        val userId = accountSession.currentUserId() ?: return
        val batch = outboxDao.getSendable(userId)
        for (row in batch) {
            outboxDao.upsert(row.copy(status = MutationOutboxEntity.STATUS_IN_FLIGHT))
        }
        val mutations = batch.map { gson.fromJson(it.payloadJson, SyncMutationDto::class.java) }
        val cursor = syncStateDao.get(userId)?.cursor
        val response = try {
            api.syncShoppingLists(SyncRequestDto(cursor, mutations), userId)
        } catch (e: Exception) {
            for (row in batch) {
                outboxDao.upsert(row.copy(status = MutationOutboxEntity.STATUS_PENDING))
            }
            throw e
        }
        applyResponse(userId, batch, response)
    }

    suspend fun resolveConflict(mutationId: String, keepLocal: Boolean) {
        val userId = requireUser()
        val conflict = conflictDao.get(mutationId, userId) ?: return
        val row = outboxDao.getByMutationId(mutationId, userId)
        if (keepLocal) {
            if (row != null) {
                val dto = gson.fromJson(row.payloadJson, SyncMutationDto::class.java)
                val serverVersion = conflict.serverJson?.let { json ->
                    JsonParser.parseString(json).asJsonObject.get("version")?.asInt
                }
                val replay = dto.copy(
                    mutation_id = UUID.randomUUID().toString(),
                    expected_version = serverVersion ?: dto.expected_version,
                )
                outboxDao.delete(mutationId)
                outboxDao.upsert(
                    row.copy(
                        mutationId = replay.mutation_id,
                        payloadJson = gson.toJson(replay),
                        status = MutationOutboxEntity.STATUS_PENDING,
                    ),
                )
            }
        } else {
            applyServerSnapshot(userId, conflict)
            row?.let { outboxDao.delete(it.mutationId) }
        }
        conflictDao.delete(mutationId)
        enqueueSync()
    }

    fun resumePendingWork() {
        syncEnqueuer.enqueueShoppingListSync()
    }

    private suspend fun patchItem(
        listId: String,
        itemId: String,
        update: (ShoppingListItemEntity) -> ShoppingListItemEntity,
        mutation: (ShoppingListItemEntity, String) -> SyncMutationDto,
    ) {
        val userId = requireUser()
        transactionRunner.run {
            val current = itemDao.get(itemId, userId) ?: error("Linjen finnes ikke")
            itemDao.upsert(update(current))
            val pending = outboxDao.findPendingItemOp(userId, itemId, MutationOutboxEntity.OP_ITEM_PATCH)
            val dto = if (pending != null) {
                mergePatch(gson.fromJson(pending.payloadJson, SyncMutationDto::class.java), mutation(current, pending.mutationId))
            } else {
                mutation(current, UUID.randomUUID().toString())
            }
            outboxDao.upsert(
                (pending ?: toOutbox(dto, userId, listId, itemId)).copy(
                    payloadJson = gson.toJson(dto),
                    operation = dto.operation,
                    listId = listId,
                    itemId = itemId,
                ),
            )
        }
        enqueueSync()
    }

    private suspend fun applyResponse(
        userId: String,
        sent: List<MutationOutboxEntity>,
        response: SyncResponseDto,
    ) {
        val conflicts = response.conflicts.associateBy { it.mutation_id }
        for (row in sent) {
            val conflict = conflicts[row.mutationId]
            if (conflict == null) {
                outboxDao.delete(row.mutationId)
                conflictDao.delete(row.mutationId)
                continue
            }
            val blocked = conflict.code == "CURSOR_EXPIRED"
            outboxDao.upsert(
                row.copy(
                    status = if (blocked) {
                        MutationOutboxEntity.STATUS_BLOCKED
                    } else {
                        MutationOutboxEntity.STATUS_CONFLICT
                    },
                ),
            )
            conflictDao.upsert(
                SyncConflictEntity(
                    mutationId = conflict.mutation_id,
                    userId = userId,
                    operation = conflict.operation,
                    code = conflict.code,
                    message = conflict.message,
                    localJson = conflict.local?.toString() ?: row.payloadJson,
                    serverJson = conflict.server?.toString(),
                    listId = row.listId,
                    itemId = row.itemId,
                ),
            )
        }

        val protecting = outboxDao.getProtecting(userId)
        val protectedLists = protecting.mapNotNull { it.listId }.toSet()
        val protectedItems = protecting.mapNotNull { it.itemId }.toSet()

        if (response.full_snapshot) {
            val snapshotListIds = response.lists.map { it.id }.toSet()
            val snapshotItemIds = response.lists.flatMap { list -> list.items.map { it.id } }.toSet()
            for (existing in listDao.getAllForUser(userId)) {
                if (existing.id !in snapshotListIds && existing.id !in protectedLists) {
                    listDao.delete(existing.id, userId)
                }
            }
            for (existing in itemDao.getAllForUser(userId)) {
                if (existing.id !in snapshotItemIds && existing.id !in protectedItems) {
                    itemDao.delete(existing.id, userId)
                }
            }
        }

        for (list in response.lists) {
            val localList = listDao.get(list.id, userId)
            val keepLocalList = list.id in protectedLists && localList != null
            if (!keepLocalList) {
                listDao.upsert(list.toEntity(userId))
            } else if (list.deleted || list.status == ShoppingListEntity.STATUS_ARCHIVED) {
                listDao.upsert(localList.copy(isDraft = true))
            }
            for (item in list.items) {
                if (item.id in protectedItems) continue
                itemDao.upsert(item.toEntity(list.id, userId))
            }
        }
        syncStateDao.upsert(SyncStateEntity(userId = userId, cursor = response.cursor))
    }

    private suspend fun applyServerSnapshot(userId: String, conflict: SyncConflictEntity) {
        val json = conflict.serverJson ?: return
        val server = JsonParser.parseString(json).asJsonObject
        val itemId = conflict.itemId ?: return
        val item = itemDao.get(itemId, userId) ?: return
        itemDao.upsert(
            item.copy(
                quantity = server.get("quantity")?.asString?.let { QuantityFormat.toJson(QuantityFormat.fromJson(it)) }
                    ?: item.quantity,
                quantityUnit = server.get("quantity_unit")?.asString ?: item.quantityUnit,
                checked = server.get("checked")?.asBoolean ?: item.checked,
                position = server.get("position")?.asInt ?: item.position,
                version = server.get("version")?.asInt ?: item.version,
                deleted = server.get("deleted")?.asBoolean ?: item.deleted,
            ),
        )
    }

    private fun requireUser(): String = checkNotNull(accountSession.currentUserId()) { "Logg inn først" }

    private fun enqueueSync() {
        syncEnqueuer.enqueueShoppingListSync()
    }

    private fun toOutbox(
        dto: SyncMutationDto,
        userId: String,
        listId: String?,
        itemId: String? = null,
    ) = MutationOutboxEntity(
        mutationId = dto.mutation_id,
        userId = userId,
        operation = dto.operation,
        listId = listId,
        itemId = itemId,
        payloadJson = gson.toJson(dto),
    )

    private fun mergePatch(existing: SyncMutationDto, incoming: SyncMutationDto) = existing.copy(
        quantity = incoming.quantity ?: existing.quantity,
        quantity_unit = incoming.quantity_unit ?: existing.quantity_unit,
        checked = incoming.checked ?: existing.checked,
        position = incoming.position ?: existing.position,
        deleted = incoming.deleted ?: existing.deleted,
    )

    private fun ShoppingListDto.toEntity(userId: String) = ShoppingListEntity(
        id = id,
        userId = userId,
        name = name,
        status = status,
        version = version,
        contentRevision = content_revision,
        deleted = deleted,
        createdAt = created_at,
        updatedAt = updated_at,
    )

    private fun ShoppingListItemDto.toEntity(listId: String, userId: String) = ShoppingListItemEntity(
        id = id,
        listId = listId,
        userId = userId,
        userProductId = user_product_id,
        freeText = free_text,
        quantity = QuantityFormat.toJson(QuantityFormat.fromJson(quantity)),
        quantityUnit = quantity_unit,
        checked = checked,
        position = position,
        version = version,
        deleted = deleted,
    )
}
