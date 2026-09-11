package no.prislapp.data.remote.dto

import com.google.gson.JsonObject

data class ShoppingListCollectionDto(
    val items: List<ShoppingListDto>,
    val next_cursor: String? = null,
)

data class ShoppingListDto(
    val id: String,
    val name: String,
    val status: String,
    val version: Int,
    val content_revision: Int,
    val deleted: Boolean = false,
    val created_at: String,
    val updated_at: String,
    val items: List<ShoppingListItemDto> = emptyList(),
)

data class ShoppingListItemDto(
    val id: String,
    val user_product_id: String? = null,
    val free_text: String? = null,
    val quantity: String,
    val quantity_unit: String,
    val checked: Boolean,
    val position: Int,
    val version: Int,
    val deleted: Boolean = false,
)

data class ShoppingListCreateRequest(
    val name: String,
    val mutation_id: String,
    val id: String? = null,
)

data class ShoppingListPatchRequest(
    val expected_version: Int,
    val mutation_id: String,
    val name: String? = null,
    val status: String? = null,
    val deleted: Boolean? = null,
)

data class ShoppingListItemUpsertRequest(
    val mutation_id: String,
    val quantity: String,
    val quantity_unit: String,
    val id: String? = null,
    val user_product_id: String? = null,
    val free_text: String? = null,
    val checked: Boolean = false,
    val position: Int? = null,
)

data class ShoppingListItemPatchRequest(
    val mutation_id: String,
    val expected_version: Int,
    val quantity: String? = null,
    val quantity_unit: String? = null,
    val checked: Boolean? = null,
    val position: Int? = null,
    val deleted: Boolean? = null,
)

data class SyncRequestDto(
    val cursor: String?,
    val mutations: List<SyncMutationDto>,
)

data class SyncMutationDto(
    val operation: String,
    val mutation_id: String,
    val list_id: String? = null,
    val item_id: String? = null,
    val id: String? = null,
    val name: String? = null,
    val expected_version: Int? = null,
    val status: String? = null,
    val deleted: Boolean? = null,
    val user_product_id: String? = null,
    val free_text: String? = null,
    val quantity: String? = null,
    val quantity_unit: String? = null,
    val checked: Boolean? = null,
    val position: Int? = null,
)

data class SyncConflictDto(
    val operation: String,
    val mutation_id: String,
    val code: String,
    val message: String,
    val field_errors: List<Map<String, String>> = emptyList(),
    val local: JsonObject? = null,
    val server: JsonObject? = null,
)

data class SyncResponseDto(
    val cursor: String,
    val price_data_version: Int,
    val full_snapshot: Boolean = false,
    val replaced_product_ids: List<Map<String, String>> = emptyList(),
    val lists: List<ShoppingListDto> = emptyList(),
    val conflicts: List<SyncConflictDto> = emptyList(),
)

data class ShoppingListPriceSummaryDto(
    val list_id: String,
    val list_version: Int,
    val content_revision: Int,
    val price_data_version: Int,
    val calculated_at: String,
    val policy_version: String,
    val include_conditional: Boolean = false,
    val lines: List<ShoppingListPriceSummaryLineDto> = emptyList(),
)

data class ShoppingListPriceSummaryLineDto(
    val item_id: String,
    val product_id: String? = null,
    val free_text: String? = null,
    val quantity: String,
    val quantity_unit: String,
    val status: String,
    val reason: String? = null,
    val eligible_store_count: Int,
    val historical_lowest: ShoppingListPriceSummaryLowestDto? = null,
)

data class ShoppingListPriceSummaryLowestDto(
    val amount: String,
    val store_id: String,
    val store_name: String,
    val identity_level: String,
    val purchase_date: String,
    val age_label: String,
    val price_basis: String,
    val disclaimer: String,
    val receipt_id: String? = null,
    val tied_stores: List<PriceSummaryTiedStoreDto> = emptyList(),
)

data class PriceSummaryTiedStoreDto(
    val store_id: String,
    val store_name: String,
    val identity_level: String,
    val purchase_date: String,
)
