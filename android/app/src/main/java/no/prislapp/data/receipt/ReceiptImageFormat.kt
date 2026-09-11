package no.prislapp.data.receipt

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import no.prislapp.R
import java.io.File

sealed class ReceiptImageSniffResult {
    data class Accepted(val mimeType: String) : ReceiptImageSniffResult()
    data class Rejected(
        val reasonCode: String,
        val messageResId: Int,
    ) : ReceiptImageSniffResult()
}

object ReceiptImageFormat {
    const val MIME_JPEG = "image/jpeg"
    const val MIME_PNG = "image/png"
    const val REASON_EMPTY = "empty"
    const val REASON_UNSUPPORTED_FORMAT = "unsupported_format"
    const val REASON_UNDECODABLE = "undecodable"
    const val JPEG_QUALITY = 90

    fun mimeFromMagic(bytes: ByteArray): String? = when {
        isJpeg(bytes) -> MIME_JPEG
        isPng(bytes) -> MIME_PNG
        else -> null
    }

    fun sniffReceiptImage(file: File): ReceiptImageSniffResult {
        if (!file.exists() || file.length() == 0L) {
            return rejected(REASON_EMPTY)
        }
        val header = file.inputStream().use { stream ->
            val buffer = ByteArray(16)
            val read = stream.read(buffer)
            if (read <= 0) byteArrayOf() else buffer.copyOf(read)
        }
        return sniffReceiptImage(header, decode = { options ->
            BitmapFactory.decodeFile(file.absolutePath, options)
        })
    }
}

fun sniffReceiptImage(bytes: ByteArray): ReceiptImageSniffResult {
    return sniffReceiptImage(bytes, decode = { options ->
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    })
}

private fun sniffReceiptImage(
    bytes: ByteArray,
    decode: (BitmapFactory.Options) -> Bitmap?,
): ReceiptImageSniffResult {
    if (bytes.isEmpty()) {
        return rejected(ReceiptImageFormat.REASON_EMPTY)
    }
    val mime = ReceiptImageFormat.mimeFromMagic(bytes) ?: return rejected(
        ReceiptImageFormat.REASON_UNSUPPORTED_FORMAT,
    )
    val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    decode(options)
    if (options.outWidth <= 0 || options.outHeight <= 0) {
        return rejected(ReceiptImageFormat.REASON_UNDECODABLE)
    }
    return ReceiptImageSniffResult.Accepted(mime)
}

fun rotateReceiptImageIfNeeded(file: File, rotationDegrees: Int): File {
    val normalized = ((rotationDegrees % 360) + 360) % 360
    if (normalized == 0) return file
    val sniff = ReceiptImageFormat.sniffReceiptImage(file)
    check(sniff is ReceiptImageSniffResult.Accepted) { "Kan ikke rotere avvist bilde" }
    val source = BitmapFactory.decodeFile(file.absolutePath)
        ?: error("Kunne ikke dekode kvitteringsbildet")
    val matrix = Matrix().apply { postRotate(normalized.toFloat()) }
    val rotated = Bitmap.createBitmap(source, 0, 0, source.width, source.height, matrix, false)
    val format = if (sniff.mimeType == ReceiptImageFormat.MIME_PNG) {
        Bitmap.CompressFormat.PNG
    } else {
        Bitmap.CompressFormat.JPEG
    }
    val quality = if (format == Bitmap.CompressFormat.JPEG) ReceiptImageFormat.JPEG_QUALITY else 100
    file.outputStream().use { output ->
        check(rotated.compress(format, quality, output)) { "Kunne ikke lagre rotert bilde" }
    }
    if (source != rotated) {
        source.recycle()
        rotated.recycle()
    }
    return file
}

private fun rejected(reasonCode: String) = ReceiptImageSniffResult.Rejected(
    reasonCode = reasonCode,
    messageResId = R.string.receipt_image_unsupported_format,
)

private fun isJpeg(bytes: ByteArray): Boolean =
    bytes.size >= 3 &&
        bytes[0] == 0xFF.toByte() &&
        bytes[1] == 0xD8.toByte() &&
        bytes[2] == 0xFF.toByte()

private fun isPng(bytes: ByteArray): Boolean =
    bytes.size >= 4 &&
        bytes[0] == 0x89.toByte() &&
        bytes[1] == 0x50.toByte() &&
        bytes[2] == 0x4E.toByte() &&
        bytes[3] == 0x47.toByte()
