package no.prislapp.data.upload

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.fail
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.FileNotFoundException
import java.io.IOException
import java.net.SocketTimeoutException

class UploadErrorClassifierTest {
    @Test
    fun http500IsRetryable() {
        assertEquals(UploadErrorKind.RETRYABLE, UploadErrorClassifier.classify(http(500)))
    }

    @Test
    fun ioExceptionIsRetryable() {
        assertEquals(UploadErrorKind.RETRYABLE, UploadErrorClassifier.classify(IOException("offline")))
    }

    @Test
    fun timeoutIsRetryable() {
        assertEquals(UploadErrorKind.RETRYABLE, UploadErrorClassifier.classify(SocketTimeoutException("timeout")))
    }

    @Test
    fun http429IsRetryable() {
        assertEquals(UploadErrorKind.RETRYABLE, UploadErrorClassifier.classify(http(429)))
    }

    @Test
    fun http413IsPermanent() {
        assertEquals(UploadErrorKind.PERMANENT, UploadErrorClassifier.classify(http(413)))
    }

    @Test
    fun http415IsPermanent() {
        assertEquals(UploadErrorKind.PERMANENT, UploadErrorClassifier.classify(http(415)))
    }

    @Test
    fun http400IsPermanent() {
        assertEquals(UploadErrorKind.PERMANENT, UploadErrorClassifier.classify(http(400)))
    }

    @Test
    fun missingFileIsPermanent() {
        assertEquals(
            UploadErrorKind.PERMANENT,
            UploadErrorClassifier.classify(FileNotFoundException("/gone.jpg")),
        )
    }

    @Test
    fun http401PausesAndIsNotPermanent() {
        val kind = UploadErrorClassifier.classify(http(401))
        assertEquals(UploadErrorKind.AUTH_PAUSE, kind)
        assertNotEquals(UploadErrorKind.PERMANENT, kind)
        assertNotEquals(UploadErrorKind.RETRYABLE, kind)
    }

    @Test
    fun cancellationIsRethrown() {
        try {
            UploadErrorClassifier.classify(kotlinx.coroutines.CancellationException("cancel"))
            fail("Must rethrow CancellationException")
        } catch (_: kotlinx.coroutines.CancellationException) {
        }
    }

    private fun http(code: Int): HttpException {
        val body = """{"detail":"error"}""".toResponseBody("application/json".toMediaType())
        return HttpException(Response.error<Any>(code, body))
    }
}
