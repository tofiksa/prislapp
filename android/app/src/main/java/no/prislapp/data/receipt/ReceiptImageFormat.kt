package no.prislapp.data.receipt

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
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
    val exifOrientation = readExifOrientation(file)
    if (normalized == 0 && isExifAlreadyNormal(exifOrientation)) {
        return file
    }
    val sniff = ReceiptImageFormat.sniffReceiptImage(file)
    check(sniff is ReceiptImageSniffResult.Accepted) { "Kan ikke rotere avvist bilde" }
    val source = BitmapFactory.decodeFile(file.absolutePath)
        ?: error("Kunne ikke dekode kvitteringsbildet")
    val rotated = bakeExifAndUserRotation(source, exifOrientation, normalized)
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
    if (format == Bitmap.CompressFormat.JPEG) {
        resetExifOrientationToNormal(file)
    }
    return file
}

private fun readExifOrientation(file: File): Int {
    return try {
        ExifInterface(file.absolutePath).getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_UNDEFINED,
        )
    } catch (_: Exception) {
        ExifInterface.ORIENTATION_UNDEFINED
    }
}

private fun isExifAlreadyNormal(orientation: Int): Boolean =
    orientation == ExifInterface.ORIENTATION_UNDEFINED ||
        orientation == ExifInterface.ORIENTATION_NORMAL

private fun bakeExifAndUserRotation(
    source: Bitmap,
    exifOrientation: Int,
    userDegrees: Int,
): Bitmap {
    if (hasExifFlip(exifOrientation)) {
        val matrix = Matrix()
        applyExifOrientation(matrix, exifOrientation)
        if (userDegrees != 0) {
            matrix.postRotate(userDegrees.toFloat())
        }
        return Bitmap.createBitmap(source, 0, 0, source.width, source.height, matrix, true)
    }
    return rotateRightAngles(source, combinedRotationDegrees(exifOrientation, userDegrees))
}

private fun combinedRotationDegrees(exifOrientation: Int, userDegrees: Int): Int {
    val exifDegrees = when (exifOrientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90
        ExifInterface.ORIENTATION_ROTATE_180 -> 180
        ExifInterface.ORIENTATION_ROTATE_270 -> 270
        else -> 0
    }
    return (exifDegrees + userDegrees) % 360
}

private fun hasExifFlip(orientation: Int): Boolean = when (orientation) {
    ExifInterface.ORIENTATION_FLIP_HORIZONTAL,
    ExifInterface.ORIENTATION_FLIP_VERTICAL,
    ExifInterface.ORIENTATION_TRANSPOSE,
    ExifInterface.ORIENTATION_TRANSVERSE,
    -> true
    else -> false
}

private fun applyExifOrientation(matrix: Matrix, orientation: Int) {
    when (orientation) {
        ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.setScale(-1f, 1f)
        ExifInterface.ORIENTATION_ROTATE_180 -> matrix.setRotate(180f)
        ExifInterface.ORIENTATION_FLIP_VERTICAL -> {
            matrix.setRotate(180f)
            matrix.postScale(-1f, 1f)
        }
        ExifInterface.ORIENTATION_TRANSPOSE -> {
            matrix.setRotate(90f)
            matrix.postScale(-1f, 1f)
        }
        ExifInterface.ORIENTATION_ROTATE_90 -> matrix.setRotate(90f)
        ExifInterface.ORIENTATION_TRANSVERSE -> {
            matrix.setRotate(-90f)
            matrix.postScale(-1f, 1f)
        }
        ExifInterface.ORIENTATION_ROTATE_270 -> matrix.setRotate(-90f)
    }
}

private fun rotateRightAngles(source: Bitmap, degrees: Int): Bitmap {
    if (degrees == 0) return source
    val srcW = source.width
    val srcH = source.height
    val destW = if (degrees == 180) srcW else srcH
    val destH = if (degrees == 180) srcH else srcW
    val dest = Bitmap.createBitmap(destW, destH, source.config ?: Bitmap.Config.ARGB_8888)
    val srcPixels = IntArray(srcW * srcH)
    source.getPixels(srcPixels, 0, srcW, 0, 0, srcW, srcH)
    val destPixels = IntArray(destW * destH)
    for (y in 0 until srcH) {
        for (x in 0 until srcW) {
            val pixel = srcPixels[y * srcW + x]
            when (degrees) {
                90 -> destPixels[x * destW + (srcH - 1 - y)] = pixel
                180 -> destPixels[(srcH - 1 - y) * destW + (srcW - 1 - x)] = pixel
                else -> destPixels[(srcW - 1 - x) * destW + y] = pixel
            }
        }
    }
    dest.setPixels(destPixels, 0, destW, 0, 0, destW, destH)
    return dest
}

private fun resetExifOrientationToNormal(file: File) {
    ExifInterface(file.absolutePath).apply {
        setAttribute(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL.toString(),
        )
        saveAttributes()
    }
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
