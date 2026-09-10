package no.prislapp.data.remote

import io.mockk.*
import no.prislapp.data.local.TokenStore
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class AuthInterceptorTest {
    @Test fun expiredSessionRefreshesAndRetriesOriginalRequest() {
        MockWebServer().use { server ->
            val store = mockk<TokenStore>(relaxed = true)
            every { store.getAccessToken() } returns "old"
            every { store.getRefreshToken() } returns "refresh"
            every { store.getUserId() } returns "user-a"
            coEvery { store.saveTokens("new", "next") } answers {
                every { store.getAccessToken() } returns "new"
            }
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Invalid token"}"""))
            server.enqueue(MockResponse().setBody("""{"access_token":"new","refresh_token":"next","token_type":"bearer"}"""))
            server.enqueue(MockResponse().setBody("ok"))
            val client = OkHttpClient.Builder().addInterceptor(AuthInterceptor(store)).build()
            client.newCall(Request.Builder().url(server.url("/receipts")).build()).execute().use {
                assertEquals(200, it.code)
            }
            assertEquals("Bearer old", server.takeRequest().getHeader("Authorization"))
            assertEquals("/auth/refresh", server.takeRequest().path)
            assertEquals("Bearer new", server.takeRequest().getHeader("Authorization"))
        }
    }

    @Test fun queuedRequestCannotUseAnotherAccountsToken() {
        MockWebServer().use { server ->
            val store = mockk<TokenStore>(relaxed = true)
            every { store.getAccessToken() } returns "token-b"
            every { store.getUserId() } returns "user-b"
            val client = OkHttpClient.Builder().addInterceptor(AuthInterceptor(store)).build()
            val request = Request.Builder().url(server.url("/receipts"))
                .header("X-Local-User", "user-a").build()
            assertThrows(java.io.IOException::class.java) { client.newCall(request).execute() }
            assertEquals(0, server.requestCount)
        }
    }
}
