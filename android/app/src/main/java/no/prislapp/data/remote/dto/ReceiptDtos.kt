package no.prislapp.data.remote.dto

import java.math.BigDecimal

data class ReceiptUploadResponse(
    val id: String,
    val status: String,
)

data class ReceiptListResponse(
    val items: List<ReceiptSummaryResponse>,
    val total: Int,
    val page: Int,
    val page_size: Int,
)

data class ReceiptSummaryResponse(
    val id: String,
    val status: String,
    val total: BigDecimal?,
    val purchase_date: String?,
    val store: StoreResponse?,
    val created_at: String,
)

data class ReceiptDetailResponse(
    val id: String,
    val status: String,
    val total: BigDecimal?,
    val purchase_date: String?,
    val store: StoreResponse?,
    val created_at: String,
    val raw_ocr_text: String?,
    val items: List<ReceiptItemResponse>,
)

data class StoreResponse(
    val id: String,
    val name: String,
    val chain: String?,
)

data class ReceiptItemResponse(
    val id: String,
    val raw_product_name: String,
    val quantity: BigDecimal,
    val unit_price: BigDecimal?,
    val line_total: BigDecimal,
)
