package no.prislapp.data.upload

import kotlinx.coroutines.CancellationException
import retrofit2.HttpException
import java.io.FileNotFoundException
import java.io.IOException

enum class UploadErrorKind {
    RETRYABLE,
    AUTH_PAUSE,
    PERMANENT,
}

object UploadErrorClassifier {
    fun classify(error: Throwable): UploadErrorKind {
        if (error is CancellationException) throw error
        return when (error) {
            is FileNotFoundException -> UploadErrorKind.PERMANENT
            is HttpException -> when (error.code()) {
                401 -> UploadErrorKind.AUTH_PAUSE
                429 -> UploadErrorKind.RETRYABLE
                in 500..599 -> UploadErrorKind.RETRYABLE
                in 400..499 -> UploadErrorKind.PERMANENT
                else -> UploadErrorKind.RETRYABLE
            }
            is IOException -> UploadErrorKind.RETRYABLE
            else -> UploadErrorKind.RETRYABLE
        }
    }

    fun errorCode(error: Throwable): String? = when (error) {
        is FileNotFoundException -> "missing_file"
        is HttpException -> error.code().toString()
        is IOException -> "network"
        else -> error::class.simpleName
    }

    fun retryAfterSeconds(error: Throwable): Long? {
        val header = (error as? HttpException)?.response()?.headers()?.get("Retry-After") ?: return null
        return header.toLongOrNull()
    }
}
