package no.prislapp.data.local

interface TransactionRunner {
    suspend fun <T> run(block: suspend () -> T): T
}
