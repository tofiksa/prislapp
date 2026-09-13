package no.prislapp.ui.navigation

import androidx.navigation.NavOptions
import androidx.navigation.navOptions

fun confirmCaptureNavOptions(): NavOptions = navOptions {
    popUpTo(Routes.SHOPPING_LIST) { saveState = false }
    launchSingleTop = true
    restoreState = false
}
