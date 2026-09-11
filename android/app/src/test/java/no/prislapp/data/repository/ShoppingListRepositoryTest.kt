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
import no.prislapp.domain.QuantityFormat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class ShoppingListRepositoryTest {
    @Test
    fun twentyOfflineMutationsSurviveProcessDeathAndEachMutationIdIsSentOnce() = runTest {
        val fixture = Fixture()
        val first = fixture.repository()
        val listId = first.createList("Ukeshandel")
        repeat(19) { first.addItem(listId, freeText = "Vare $it") }
        assertEquals(20, fixture.db.outbox.size)

        val sentIds = mutableListOf<String>()
        coEvery { fixture.api.syncShoppingLists(any(), any()) } answers {
            val body = firstArg<SyncRequestDto>()
            sentIds += body.mutations.map { it.mutation_id }
            okSync()
        }

        val afterDeath = fixture.repository()
        afterDeath.syncPending()
        afterDeath.syncPending()

        assertEquals(20, sentIds.size)
        assertEquals(sentIds.toSet().size, sentIds.size)
        assertTrue(afterDeath.pendingMutations().isEmpty())
    }

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
        assertEquals(3, repository.pendingMutations().size)
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

    private class Fixture {
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
            outboxDao = FakeMutationOutboxDao(db),
            conflictDao = FakeSyncConflictDao(db),
            syncStateDao = FakeSyncStateDao(db),
            productCacheDao = FakeCachedUserProductDao(db),
            accountSession = session,
            syncEnqueuer = SyncEnqueuer { },
            transactionRunner = object : TransactionRunner {
                override suspend fun <T> run(block: suspend () -> T): T = block()
            },
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
