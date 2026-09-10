package no.prislapp.data.repository

import io.mockk.*
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import no.prislapp.data.local.TokenStore
import no.prislapp.data.remote.PrislappApi
import no.prislapp.data.remote.dto.TokenResponse
import org.junit.Test
import org.junit.Assert.*

class AuthRepositoryTest {
    @Test fun failedProfileLookupDoesNotPublishLoggedInSession() = runTest {
        val api = mockk<PrislappApi>()
        val store = mockk<TokenStore>(relaxed = true)
        every { store.isLoggedIn } returns flowOf(false)
        coEvery { api.login(any()) } returns TokenResponse("access", "refresh", "bearer")
        coEvery { api.getMe(any()) } throws java.io.IOException("offline")
        val result = AuthRepository(api, store).login("a@example.com", "password")
        assertTrue(result.isFailure)
        coVerify(exactly = 0) { store.saveTokens(any(), any()) }
    }
}
