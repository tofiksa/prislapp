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
import no.prislapp.data.remote.dto.ShoppingListFromReceiptRequest
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

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeRecentProducts(): Flow<List<CachedUserProductEntity>> =
        accountSession.observeUserId().flatMapLatest { user ->
            if (user == null) flowOf(emptyList()) else productCacheDao.observeForUser(user)
        }

    suspend fun refreshRecentProducts() {
        val userId = requireUser()
        val response = api.listMyProducts(sort = "recent")
        transactionRunner.run {
            for (product in response.items) {
                productCacheDao.upsert(
                    CachedUserProductEntity(
                        id = product.id,
                        userId = userId,
                        displayName = product.display_name,
                        packContent = product.pack_content,
                        packUnit = product.pack_unit,
                        lastPurchasedAt = product.last_purchased_at,
                    ),
                )
            }
        }
    }

    suspend fun addProductOrIncrement(
        listId: String,
        userProductId: String,
        productDisplayName: String,
        quantity: BigDecimal = BigDecimal.ONE,
        quantityUnit: String = "each",
    ): AddItemResult {
        val userId = requireUser()
        val existing = itemDao.findOpenProductLine(listId, userId, userProductId, quantityUnit)
        if (existing != null) {
            val previous = QuantityFormat.fromJson(existing.quantity)
            setItemQuantity(listId, existing.id, previous + quantity)
            return AddItemResult(itemId = existing.id, previousQuantity = previous)
        }
        val itemId = addItem(
            listId = listId,
            userProductId = userProductId,
            productDisplayName = productDisplayName,
            quantity = quantity,
            quantityUnit = quantityUnit,
        )
        return AddItemResult(itemId = itemId)
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
                val cached = productCacheDao.get(userProductId, userId)
                productCacheDao.upsert(
                    CachedUserProductEntity(
                        id = userProductId,
                        userId = userId,
                        displayName = productDisplayName,
                        packContent = cached?.packContent,
                        packUnit = cached?.packUnit ?: quantityUnit,
                        lastPurchasedAt = cached?.lastPurchasedAt,
                    ),
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

    suspend fun setItemDeleted(listId: String, itemId: String, deleted: Boolean = true) {
        patchItem(listId, itemId, { it.copy(deleted = deleted) }) { current, mutationId ->
            SyncMutationDto(
                operation = MutationOutboxEntity.OP_ITEM_PATCH,
                mutation_id = mutationId,
                list_id = listId,
                item_id = itemId,
                expected_version = current.version,
                deleted = deleted,
            )
        }
    }

    suspend fun setListDeleted(listId: String, deleted: Boolean = true) {
        patchList(listId, { it.copy(deleted = deleted) }) { current, mutationId ->
            SyncMutationDto(
                operation = MutationOutboxEntity.OP_LIST_PATCH,
                mutation_id = mutationId,
                list_id = listId,
                expected_version = current.version,
                deleted = deleted,
            )
        }
    }

    suspend fun setListArchived(listId: String, archived: Boolean) {
        val status = if (archived) {
            ShoppingListEntity.STATUS_ARCHIVED
        } else {
            ShoppingListEntity.STATUS_ACTIVE
        }
        patchList(listId, { it.copy(status = status) }) { current, mutationId ->
            SyncMutationDto(
                operation = MutationOutboxEntity.OP_LIST_PATCH,
                mutation_id = mutationId,
                list_id = listId,
                expected_version = current.version,
                status = status,
            )
        }
    }

    suspend fun copyList(listId: String, uncheckedOnly: Boolean = false): String {
        val userId = requireUser()
        val newListId = UUID.randomUUID().toString()
        val now = Instant.now().toString()
        transactionRunner.run {
            val source = listDao.get(listId, userId) ?: error("Listen finnes ikke")
            val sourceItems = itemDao.getForList(listId, userId)
                .filter { !it.deleted }
                .filter { !uncheckedOnly || !it.checked }
            listDao.upsert(
                ShoppingListEntity(
                    id = newListId,
                    userId = userId,
                    name = source.name,
                    createdAt = now,
                    updatedAt = now,
                ),
            )
            outboxDao.upsert(
                toOutbox(
                    SyncMutationDto(
                        operation = MutationOutboxEntity.OP_LIST_CREATE,
                        mutation_id = UUID.randomUUID().toString(),
                        id = newListId,
                        name = source.name,
                    ),
                    userId,
                    listId = newListId,
                ),
            )
            sourceItems.forEachIndexed { index, item ->
                val itemId = UUID.randomUUID().toString()
                itemDao.upsert(
                    ShoppingListItemEntity(
                        id = itemId,
                        listId = newListId,
                        userId = userId,
                        userProductId = item.userProductId,
                        freeText = item.freeText,
                        quantity = item.quantity,
                        quantityUnit = item.quantityUnit,
                        checked = false,
                        position = index,
                    ),
                )
                outboxDao.upsert(
                    toOutbox(
                        SyncMutationDto(
                            operation = MutationOutboxEntity.OP_ITEM_CREATE,
                            mutation_id = UUID.randomUUID().toString(),
                            list_id = newListId,
                            id = itemId,
                            user_product_id = item.userProductId,
                            free_text = item.freeText,
                            quantity = item.quantity,
                            quantity_unit = item.quantityUnit,
                            checked = false,
                            position = index,
                        ),
                        userId,
                        listId = newListId,
                        itemId = itemId,
                    ),
                )
            }
        }
        enqueueSync()
        return newListId
    }

    suspend fun copyFromReceipt(receiptId: String): String {
        val userId = requireUser()
        val response = api.createShoppingListFromReceipt(
            ShoppingListFromReceiptRequest(
                receipt_id = receiptId,
                mutation_id = UUID.randomUUID().toString(),
                id = UUID.randomUUID().toString(),
            ),
            userId,
        )
        transactionRunner.run {
            persistServerList(response, userId)
        }
        return response.id
    }

    suspend fun finishTrip(listId: String, keepUnchecked: Boolean): String {
        val newId = if (keepUnchecked) {
            copyList(listId, uncheckedOnly = true)
        } else {
            createList(DEFAULT_NEW_LIST_NAME)
        }
        setListArchived(listId, true)
        return newId
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

    private suspend fun patchList(
        listId: String,
        update: (ShoppingListEntity) -> ShoppingListEntity,
        mutation: (ShoppingListEntity, String) -> SyncMutationDto,
    ) {
        val userId = requireUser()
        transactionRunner.run {
            val current = listDao.get(listId, userId) ?: error("Listen finnes ikke")
            listDao.upsert(update(current))
            val dto = mutation(current, UUID.randomUUID().toString())
            outboxDao.upsert(toOutbox(dto, userId, listId))
        }
        enqueueSync()
    }

    private suspend fun applyResponse(
        userId: String,
        sent: List<MutationOutboxEntity>,
        response: SyncResponseDto,
    ) {
        transactionRunner.run {
            val conflicts = response.conflicts.associateBy { it.mutation_id }
            for (row in sent) {
                val conflict = conflicts[row.mutationId]
                if (conflict == null) {
                    outboxDao.delete(row.mutationId)
                    conflictDao.delete(row.mutationId)
                    continue
                }
                if (conflict.code == "CURSOR_EXPIRED") {
                    outboxDao.upsert(row.copy(status = MutationOutboxEntity.STATUS_PENDING))
                    conflictDao.delete(row.mutationId)
                    continue
                }
                outboxDao.upsert(row.copy(status = MutationOutboxEntity.STATUS_CONFLICT))
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

    private suspend fun persistServerList(list: ShoppingListDto, userId: String) {
        listDao.upsert(list.toEntity(userId))
        for (item in list.items) {
            itemDao.upsert(item.toEntity(list.id, userId))
        }
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

    companion object {
        const val DEFAULT_NEW_LIST_NAME = "Handleliste"
    }
}
