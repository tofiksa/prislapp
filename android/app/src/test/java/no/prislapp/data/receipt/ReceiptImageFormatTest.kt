package no.prislapp.data.receipt

import android.graphics.Bitmap
import androidx.test.ext.junit.runners.AndroidJUnit4
import no.prislapp.R
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream

@RunWith(AndroidJUnit4::class)
class ReceiptImageFormatTest {
    @Test
    fun miniatureJpegIsAcceptedAsJpeg() {
        val result = sniffReceiptImage(miniatureJpeg())
        assertTrue(result is ReceiptImageSniffResult.Accepted)
        assertEquals("image/jpeg", (result as ReceiptImageSniffResult.Accepted).mimeType)
    }

    @Test
    fun miniaturePngIsAcceptedAsPng() {
        val result = sniffReceiptImage(miniaturePng())
        assertTrue(result is ReceiptImageSniffResult.Accepted)
        assertEquals("image/png", (result as ReceiptImageSniffResult.Accepted).mimeType)
    }

    @Test
    fun pdfHeaderIsRejectedWithUnsupportedFormat() {
        val result = sniffReceiptImage("%PDF-1.4\n".toByteArray())
        assertRejected(result, "unsupported_format")
    }

    @Test
    fun emptyBytesAreRejected() {
        val result = sniffReceiptImage(byteArrayOf())
        assertRejected(result, "empty")
    }

    @Test
    fun randomBytesAreRejected() {
        val result = sniffReceiptImage(byteArrayOf(0x01, 0x02, 0x03, 0x04, 0x05))
        assertRejected(result, "unsupported_format")
    }

    @Test
    fun webpHeaderIsRejected() {
        val result = sniffReceiptImage("RIFF\u0000\u0000\u0000\u0000WEBPVP8 ".toByteArray(Charsets.ISO_8859_1))
        assertRejected(result, "unsupported_format")
    }

    @Test
    fun heicHeaderIsRejected() {
        val header = ByteArray(12)
        header[4] = 'f'.code.toByte()
        header[5] = 't'.code.toByte()
        header[6] = 'y'.code.toByte()
        header[7] = 'p'.code.toByte()
        header[8] = 'h'.code.toByte()
        header[9] = 'e'.code.toByte()
        header[10] = 'i'.code.toByte()
        header[11] = 'c'.code.toByte()
        val result = sniffReceiptImage(header)
        assertRejected(result, "unsupported_format")
    }

    @Test
    fun htmlIsRejected() {
        val result = sniffReceiptImage("<!DOCTYPE html><html></html>".toByteArray())
        assertRejected(result, "unsupported_format")
    }

    @Test
    fun rotateNinetySwapsDimensionsWithoutShrinking() {
        val bitmap = Bitmap.createBitmap(8, 4, Bitmap.Config.ARGB_8888)
        val file = java.io.File.createTempFile("rotate", ".png")
        try {
            file.outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            val rotated = rotateReceiptImageIfNeeded(file, 90)
            val decoded = android.graphics.BitmapFactory.decodeFile(rotated.absolutePath)
            assertEquals(4, decoded.width)
            assertEquals(8, decoded.height)
        } finally {
            file.delete()
        }
    }

    @Test
    fun zeroRotationDoesNotRewriteJpeg() {
        val original = miniatureJpeg()
        val file = java.io.File.createTempFile("norot", ".jpg")
        try {
            file.writeBytes(original)
            rotateReceiptImageIfNeeded(file, 0)
            assertTrue(original.contentEquals(file.readBytes()))
        } finally {
            file.delete()
        }
    }

    private fun assertRejected(result: ReceiptImageSniffResult, reasonCode: String) {
        assertTrue(result is ReceiptImageSniffResult.Rejected)
        val rejected = result as ReceiptImageSniffResult.Rejected
        assertEquals(reasonCode, rejected.reasonCode)
        assertEquals(R.string.receipt_image_unsupported_format, rejected.messageResId)
    }

    private fun miniatureJpeg(): ByteArray {
        val bitmap = Bitmap.createBitmap(2, 2, Bitmap.Config.ARGB_8888)
        val out = ByteArrayOutputStream()
        check(bitmap.compress(Bitmap.CompressFormat.JPEG, 90, out))
        return out.toByteArray()
    }

    private fun miniaturePng(): ByteArray {
        val bitmap = Bitmap.createBitmap(2, 2, Bitmap.Config.ARGB_8888)
        val out = ByteArrayOutputStream()
        check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out))
        return out.toByteArray()
    }
}
