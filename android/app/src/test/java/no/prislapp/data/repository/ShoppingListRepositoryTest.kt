package no.prislapp.data.repository

import com.google.gson.Gson
import com.google.gson.JsonObject
import io.mockk.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.AccountSession
import no.prislapp.data.local.FakeCachedUserProductDao
import no.prislapp.data.local.FakeMutationOutboxDao
import no.prislapp.data.local.FakeShoppingListDao
import no.prislapp.data.local.FakeShoppingListItemDao
import no.prislapp.data.local.FakeSyncConflictDao
import no.prislapp.data.local.FakeSyncStateDao
import no.prislapp.data.local.ShoppingListMemoryDb
import no.prislapp.data.local.SyncEnqueuer
import no.prislapp.data.local.TransactionRunner
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.ShoppingListDto
import no.prislapp.data.remote.dto.ShoppingListItemDto
import no.prislapp.data.remote.dto.SyncConflictDto
import no.prislapp.data.remote.dto.SyncRequestDto
import no.prislapp.data.remote.dto.SyncResponseDto
import no.prislapp.data.remote.dto.UserProductListResponse
import no.prislapp.data.remote.dto.UserProductResponse
import no.prislapp.domain.QuantityFormat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class ShoppingListRepositoryTest {
    @Test
    fun queriesForAccountBAreEmptyOfAccountARows() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        repository.createList("A sin liste")

        fixture.userId.value = "user-b"
        assertTrue(repository.observeLists().first().isEmpty())
        assertTrue(repository.pendingMutations().isEmpty())
        assertTrue(fixture.db.lists.none { it.userId == "user-b" })

        fixture.userId.value = "user-a"
        assertEquals(listOf("A sin liste"), repository.observeLists().first().map { it.name })
    }

    @Test
    fun quantityConflictKeepsLocalValueUntilResolved() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val itemId = repository.addItem(listId, freeText = "Melk")
        repository.setItemQuantity(listId, itemId, BigDecimal("9"))
        assertEquals("9.000", repository.getItem(itemId)?.quantity)

        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            val body = firstArg<SyncRequestDto>()
            val quantityPatch = body.mutations.single { it.operation == "item_patch" }
            SyncResponseDto(
                cursor = "c1",
                price_data_version = 1,
                full_snapshot = false,
                lists = listOf(
                    listDto(
                        listId,
                        itemDto(itemId, quantity = "4.000", version = 2),
                    ),
                ),
                conflicts = listOf(
                    SyncConflictDto(
                        operation = "item_patch",
                        mutation_id = quantityPatch.mutation_id,
                        code = "VERSION_CONFLICT",
                        message = "Raden er endret et annet sted.",
                        local = JsonObject().apply { addProperty("quantity", "9.000") },
                        server = JsonObject().apply {
                            addProperty("quantity", "4.000")
                            addProperty("version", 2)
                        },
                    ),
                ),
            )
        }

        repository.syncPending()

        val item = repository.getItem(itemId)!!
        assertEquals("9.000", item.quantity)
        val conflict = fixture.db.conflicts.single()
        assertEquals("VERSION_CONFLICT", conflict.code)
        assertTrue(conflict.localJson.contains("9.000"))
        assertTrue(conflict.serverJson!!.contains("4.000"))
        assertEquals("9.000", repository.observeConflicts().first().single().let { item.quantity })
    }

    @Test
    fun checkingAnItemEnqueuesItemPatchCheckedTrueWithoutCallingPriceApis() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val requests = mutableListOf<SyncRequestDto>()
        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            requests += firstArg<SyncRequestDto>()
            okSync()
        }

        val listId = repository.createList("Tur")
        val itemId = repository.addItem(listId, freeText = "Melk")
        repository.syncPending()
        repository.setItemChecked(listId, itemId, true)
        repository.syncPending()

        val last = requests.last().mutations.single()
        assertEquals("item_patch", last.operation)
        assertEquals(true, last.checked)
        assertEquals(itemId, last.item_id)
        assertEquals("1.000", QuantityFormat.toJson(BigDecimal.ONE))
        coVerify(exactly = 0) { fixture.api.getProductPrices(any()) }
        coVerify(exactly = 0) { fixture.api.searchProducts(any()) }
        coVerify(exactly = 0) { fixture.api.createShoppingList(any(), any()) }
    }

    @Test
    fun expiredCursorKeepsPendingMutationsAndDoesNotOverwriteLocalQuantity() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val itemId = repository.addItem(listId, freeText = "Melk")
        repository.setItemQuantity(listId, itemId, BigDecimal("9"))

        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            val body = firstArg<SyncRequestDto>()
            SyncResponseDto(
                cursor = "fresh",
                price_data_version = 1,
                full_snapshot = true,
                lists = listOf(listDto(listId, itemDto(itemId, quantity = "1.000", version = 1))),
                conflicts = body.mutations.map {
                    SyncConflictDto(
                        operation = it.operation,
                        mutation_id = it.mutation_id,
                        code = "CURSOR_EXPIRED",
                        message = "Synkroniseringsmarkøren kan ikke brukes.",
                    )
                },
            )
        }

        repository.syncPending()

        assertEquals("9.000", repository.getItem(itemId)?.quantity)
        val originalIds = repository.pendingMutations()
        assertEquals(3, originalIds.size)
        assertTrue(fixture.db.conflicts.none { it.code == "CURSOR_EXPIRED" })

        val replayed = mutableListOf<String>()
        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            replayed += firstArg<SyncRequestDto>().mutations.map { it.mutation_id }
            okSync()
        }
        repository.syncPending()

        assertEquals(originalIds, replayed)
        assertTrue(repository.pendingMutations().isEmpty())
    }

    @Test
    fun localDeleteVersusServerQuantityStaysConflictAndKeepsTombstone() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val itemId = repository.addItem(listId, freeText = "Melk")
        repository.setItemDeleted(listId, itemId)
        assertEquals(true, repository.getItem(itemId)?.deleted)

        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            val body = firstArg<SyncRequestDto>()
            val deletePatch = body.mutations.single { it.deleted == true }
            SyncResponseDto(
                cursor = "c1",
                price_data_version = 1,
                full_snapshot = false,
                lists = listOf(
                    listDto(listId, itemDto(itemId, quantity = "4.000", version = 2)),
                ),
                conflicts = listOf(
                    SyncConflictDto(
                        operation = "item_patch",
                        mutation_id = deletePatch.mutation_id,
                        code = "VERSION_CONFLICT",
                        message = "Raden er endret et annet sted.",
                        local = JsonObject().apply { addProperty("deleted", true) },
                        server = JsonObject().apply {
                            addProperty("quantity", "4.000")
                            addProperty("version", 2)
                        },
                    ),
                ),
            )
        }

        repository.syncPending()

        assertEquals(true, repository.getItem(itemId)?.deleted)
        val conflict = fixture.db.conflicts.single()
        assertEquals("VERSION_CONFLICT", conflict.code)
        assertTrue(conflict.localJson.contains("deleted"))
    }

    @Test
    fun applyResponseDeletesSendableIdsOnlyInsideTransaction() = runTest {
        val inTransaction = java.util.concurrent.atomic.AtomicBoolean(false)
        val deletedOutside = mutableListOf<String>()
        val fixture = Fixture(
            transactionRunner = object : TransactionRunner {
                override suspend fun <T> run(block: suspend () -> T): T {
                    inTransaction.set(true)
                    try {
                        return block()
                    } finally {
                        inTransaction.set(false)
                    }
                }
            },
            outboxDao = { db ->
                object : FakeMutationOutboxDao(db) {
                    override suspend fun delete(mutationId: String) {
                        if (!inTransaction.get()) deletedOutside += mutationId
                        super.delete(mutationId)
                    }
                }
            },
        )
        val repository = fixture.repository()
        repository.createList("Tur")
        coEvery { fixture.api.syncShoppingLists(any(), any()) } returns okSync()

        repository.syncPending()

        assertTrue(deletedOutside.isEmpty())
        assertTrue(repository.pendingMutations().isEmpty())
    }

    @Test
    fun quantityIsSerializedAsJsonStringNotNumber() {
        val json = Gson().toJson(
            no.prislapp.data.remote.dto.SyncMutationDto(
                operation = "item_patch",
                mutation_id = "11111111-1111-1111-1111-111111111111",
                quantity = QuantityFormat.toJson(BigDecimal.ONE),
            ),
        )
        assertTrue(json.contains("\"quantity\":\"1.000\""))
        assertFalse(json.contains("\"quantity\":1"))
    }

    @Test
    fun addProductOrIncrementMergesUncheckedSameProductAndUnit() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val first = repository.addProductOrIncrement(listId, "prod-1", "Melk")
        val second = repository.addProductOrIncrement(listId, "prod-1", "Melk")

        assertEquals(first.itemId, second.itemId)
        assertEquals(null, first.previousQuantity)
        assertEquals(0, BigDecimal.ONE.compareTo(second.previousQuantity))
        assertEquals("2.000", repository.getItem(first.itemId)?.quantity)
        assertEquals(1, fixture.db.items.count { !it.deleted })
    }

    @Test
    fun addProductOrIncrementDoesNotMergeFreeTextWithSameName() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val free = repository.addItem(listId, freeText = "Melk")
        val product = repository.addProductOrIncrement(listId, "prod-1", "Melk")

        assertTrue(free != product.itemId)
        assertEquals(2, fixture.db.items.count { !it.deleted })
        assertEquals("Melk", repository.getItem(free)?.freeText)
        assertEquals("prod-1", repository.getItem(product.itemId)?.userProductId)
    }

    @Test
    fun addProductOrIncrementDoesNotMergeCheckedLine() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val first = repository.addProductOrIncrement(listId, "prod-1", "Melk")
        repository.setItemChecked(listId, first.itemId, true)
        val second = repository.addProductOrIncrement(listId, "prod-1", "Melk")

        assertTrue(first.itemId != second.itemId)
        assertEquals(null, second.previousQuantity)
        assertEquals(2, fixture.db.items.count { !it.deleted })
    }

    @Test
    fun refreshRecentProductsCachesPackFieldsFromDecimalStrings() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        coEvery { fixture.api.listMyProducts(sort = "recent") } returns UserProductListResponse(
            items = listOf(
                UserProductResponse(
                    id = "prod-1",
                    display_name = "Melk",
                    pack_content = "1.000",
                    pack_unit = "l",
                    last_purchased_at = "2026-09-01",
                    purchase_count = 3,
                    version = 1,
                    identity_status = "confirmed",
                ),
            ),
        )

        repository.refreshRecentProducts()

        val cached = repository.observeRecentProducts().first().single()
        assertEquals("Melk", cached.displayName)
        assertEquals("1.000", cached.packContent)
        assertEquals("l", cached.packUnit)
        assertEquals("2026-09-01", cached.lastPurchasedAt)
        val json = Gson().toJson(
            UserProductResponse(
                id = "prod-1",
                display_name = "Melk",
                pack_content = "1.000",
                pack_unit = "l",
                identity_status = "confirmed",
                purchase_count = 3,
                version = 1,
            ),
        )
        assertTrue(json.contains("\"pack_content\":\"1.000\""))
        assertFalse(json.contains("\"pack_content\":1"))
    }

    @Test
    fun copyListAssignsNewIdsUncheckedAndDoesNotCallIncrement() = runTest {
        val fixture = Fixture()
        val repository = spyk(fixture.repository())
        val listId = repository.createList("Tur")
        val checkedId = repository.addItem(listId, freeText = "Melk")
        repository.addItem(listId, userProductId = "p-melk", productDisplayName = "Melk")
        repository.setItemChecked(listId, checkedId, true)

        val copyId = repository.copyList(listId)

        assertTrue(copyId != listId)
        val copies = fixture.db.items.filter { it.listId == copyId && !it.deleted }.sortedBy { it.position }
        val sources = fixture.db.items.filter { it.listId == listId && !it.deleted }
        assertEquals(2, copies.size)
        assertEquals(sources.size, copies.size)
        assertTrue(copies.all { !it.checked })
        assertTrue(copies.none { source -> sources.any { it.id == source.id } })
        assertEquals(listOf("Melk", null), copies.map { it.freeText })
        coVerify(exactly = 0) { repository.addProductOrIncrement(any(), any(), any(), any(), any()) }
        val copyOps = fixture.db.outbox.filter { it.listId == copyId }.map { it.operation }
        assertEquals("list_create", copyOps.first())
        assertTrue(copyOps.drop(1).all { it == "item_create" })
    }

    @Test
    fun finishTripKeepingUncheckedArchivesSourceAndCopiesOpenLines() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        val keepId = repository.addItem(listId, freeText = "Brød")
        val dropId = repository.addItem(listId, freeText = "Melk")
        repository.setItemChecked(listId, dropId, true)

        val newId = repository.finishTrip(listId, keepUnchecked = true)

        assertEquals("archived", fixture.db.lists.single { it.id == listId }.status)
        assertEquals("active", fixture.db.lists.single { it.id == newId }.status)
        val copies = fixture.db.items.filter { it.listId == newId && !it.deleted }
        assertEquals(listOf("Brød"), copies.map { it.freeText })
        assertTrue(copies.single().id != keepId)
        assertFalse(copies.single().checked)
    }

    @Test
    fun finishTripWithoutKeepingArchivesAndLeavesANewActiveList() = runTest {
        val fixture = Fixture()
        val repository = fixture.repository()
        val listId = repository.createList("Tur")
        repository.addItem(listId, freeText = "Melk")

        val newId = repository.finishTrip(listId, keepUnchecked = false)

        assertTrue(newId != listId)
        assertEquals("archived", fixture.db.lists.single { it.id == listId }.status)
        assertEquals("active", fixture.db.lists.single { it.id == newId }.status)
        assertTrue(fixture.db.items.none { it.listId == newId && !it.deleted })
    }

    private class Fixture(
        private val transactionRunner: TransactionRunner = object : TransactionRunner {
            override suspend fun <T> run(block: suspend () -> T): T = block()
        },
        private val outboxDao: (ShoppingListMemoryDb) -> FakeMutationOutboxDao = { FakeMutationOutboxDao(it) },
    ) {
        val db = ShoppingListMemoryDb()
        val userId = MutableStateFlow<String?>("user-a")
        val api = mockk<PrislappApi>(relaxed = true)
        private val session = object : AccountSession {
            override fun currentUserId() = userId.value
            override fun observeUserId() = userId
        }

        fun repository(): ShoppingListRepository = ShoppingListRepository(
            api = api,
            listDao = FakeShoppingListDao(db),
            itemDao = FakeShoppingListItemDao(db),
            outboxDao = outboxDao(db),
            conflictDao = FakeSyncConflictDao(db),
            syncStateDao = FakeSyncStateDao(db),
            productCacheDao = FakeCachedUserProductDao(db),
            accountSession = session,
            syncEnqueuer = SyncEnqueuer { },
            transactionRunner = transactionRunner,
        )
    }

    private fun okSync() = SyncResponseDto(
        cursor = "cursor-1",
        price_data_version = 1,
        full_snapshot = false,
    )

    private fun listDto(id: String, vararg items: ShoppingListItemDto) = ShoppingListDto(
        id = id,
        name = "Tur",
        status = "active",
        version = 1,
        content_revision = 2,
        created_at = "2026-01-01T00:00:00Z",
        updated_at = "2026-01-01T00:00:00Z",
        items = items.toList(),
    )

    private fun itemDto(id: String, quantity: String, version: Int) = ShoppingListItemDto(
        id = id,
        free_text = "Melk",
        quantity = quantity,
        quantity_unit = "each",
        checked = false,
        position = 0,
        version = version,
    )
}
