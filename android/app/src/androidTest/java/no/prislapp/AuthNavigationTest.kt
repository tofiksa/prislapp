package no.prislapp

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AuthNavigationTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun loginHistorySearchAndLogoutAgainstLocalBackend() {
        // Explicit opt-in: never create test accounts against the default hosted API.
        org.junit.Assume.assumeTrue(BuildConfig.API_BASE_URL.contains("10.0.2.2:18000"))
        val email = "android-${System.currentTimeMillis()}@example.com"
        val json = """{"email":"$email","password":"TestPass123!"}"""
        OkHttpClient().newCall(Request.Builder().url(BuildConfig.API_BASE_URL + "auth/register")
            .post(json.toRequestBody("application/json".toMediaType())).build()).execute().use {
            org.junit.Assert.assertEquals(201, it.code)
        }
        compose.onNodeWithText("E-post").performTextInput(email)
        compose.onNodeWithText("Passord").performTextInput("TestPass123!")
        compose.onAllNodesWithText("Logg inn").filterToOne(hasClickAction()).performClick()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithContentDescription("Ta bilde av kvittering").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Historikk").performClick()
        compose.onNodeWithText("Søk").performClick()
        compose.onNode(hasSetTextAction()).performTextInput("melk")
        compose.waitUntil(15_000) {
            compose.onAllNodesWithText("Ingen produkter funnet i dine bekreftede kvitteringer").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Hjem").performClick()
        compose.onNodeWithContentDescription("Konto").performClick()
        compose.onNodeWithText("Logg ut").performClick()
        compose.waitUntil(10_000) { compose.onAllNodesWithText("Passord").fetchSemanticsNodes().isNotEmpty() }
    }
}
