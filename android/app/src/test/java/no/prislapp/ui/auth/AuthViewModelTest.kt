package no.prislapp.ui.auth

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import no.prislapp.data.repository.AuthRepository
import no.prislapp.domain.model.User
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private lateinit var authRepository: AuthRepository
    private lateinit var googleSignInHelper: GoogleSignInHelper
    private lateinit var viewModel: AuthViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        authRepository = mockk(relaxed = true)
        googleSignInHelper = mockk(relaxed = true)
        viewModel = AuthViewModel(authRepository, googleSignInHelper)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun loginSuccess_updatesUiStateToLoggedIn() = runTest {
        coEvery { authRepository.login(any(), any()) } returns Result.success(
            User(id = "1", email = "test@example.com"),
        )

        viewModel.login("test@example.com", "TestPass123!")
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value.isLoggedIn)
        assertEquals("test@example.com", viewModel.uiState.value.user?.email)
    }
}
