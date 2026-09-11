package no.prislapp.ui.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class LoggedInNavigationTest {
    @Test
    fun loggedInStartRouteIsShoppingList() {
        assertEquals(Routes.SHOPPING_LIST, Routes.LOGGED_IN_START)
    }

    @Test
    fun tabRoutesAreHandlelisteVarerKvitteringer() {
        assertEquals(3, Routes.TAB_ROUTES.size)
        assertEquals(
            setOf(Routes.SHOPPING_LIST, Routes.PRODUCT_SEARCH, Routes.RECEIPTS),
            Routes.TAB_ROUTES,
        )
        assertFalse(Routes.TAB_ROUTES.contains(Routes.HOME))
        assertFalse(Routes.TAB_ROUTES.contains(Routes.HISTORY))
    }

    @Test
    fun confirmCaptureDoesNotSaveOrRestoreTabState() {
        val options = confirmCaptureNavOptions()
        assertEquals(Routes.SHOPPING_LIST, options.popUpToRoute)
        assertFalse(options.shouldPopUpToSaveState())
        assertFalse(options.shouldRestoreState())
        assertFalse(options.isPopUpToInclusive())
    }
}
