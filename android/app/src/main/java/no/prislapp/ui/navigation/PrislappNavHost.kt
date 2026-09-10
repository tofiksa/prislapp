package no.prislapp.ui.navigation

import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import no.prislapp.R
import no.prislapp.ui.auth.AuthViewModel
import no.prislapp.ui.auth.LoginScreen
import no.prislapp.ui.auth.RegisterScreen
import no.prislapp.ui.camera.CameraScreen
import no.prislapp.ui.history.HistoryScreen
import no.prislapp.ui.home.HomeScreen
import no.prislapp.ui.product.ProductPricesScreen
import no.prislapp.ui.product.ProductSearchScreen
import no.prislapp.ui.receipt.ReceiptProcessingScreen
import no.prislapp.ui.receipt.ReceiptReviewScreen

private data class BottomTab(
    val route: String,
    val icon: ImageVector,
    val labelRes: Int,
)

@Composable
fun PrislappNavHost(
    authViewModel: AuthViewModel = hiltViewModel(),
) {
    val navController = rememberNavController()
    val uiState by authViewModel.uiState.collectAsStateWithLifecycle()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route
    val tabRoutes = Routes.TAB_ROUTES
    val showBottomBar = currentRoute in tabRoutes

    LaunchedEffect(uiState.isLoggedIn) {
        if (uiState.isLoggedIn) {
            navController.navigate(Routes.HOME) {
                popUpTo(navController.graph.id) { inclusive = true }
                launchSingleTop = true
            }
        } else {
            navController.navigate(Routes.LOGIN) {
                popUpTo(navController.graph.id) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (showBottomBar) {
                LoggedInBottomBar(
                    currentRoute = currentRoute,
                    onNavigate = { route -> navController.navigateToTab(route) },
                )
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Routes.LOGIN,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(Routes.LOGIN) {
                LoginScreen(
                    viewModel = authViewModel,
                    onNavigateToRegister = { navController.navigate(Routes.REGISTER) },
                    onLoggedIn = {},
                )
            }
            composable(Routes.REGISTER) {
                RegisterScreen(
                    viewModel = authViewModel,
                    onNavigateToLogin = { navController.popBackStack() },
                    onRegistered = {},
                )
            }
            composable(Routes.HOME) {
                HomeScreen(
                    onCaptureReceipt = { navController.navigate(Routes.CAMERA) },
                    onOpenReceipt = { receiptId ->
                        navController.navigate(Routes.review(receiptId))
                    },
                    onOpenPending = { localId ->
                        navController.navigate(Routes.processing(localId))
                    },
                    onLogout = { authViewModel.logout() },
                )
            }
            composable(Routes.CAMERA) {
                CameraScreen(
                    onCaptured = { localId ->
                        navController.navigate(Routes.processing(localId)) {
                            popUpTo(Routes.HOME)
                        }
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(
                route = Routes.PROCESSING,
                arguments = listOf(navArgument("localId") { type = NavType.LongType }),
            ) {
                ReceiptProcessingScreen(
                    onReadyForReview = { receiptId ->
                        navController.navigate(Routes.review(receiptId)) {
                            popUpTo(Routes.HOME)
                        }
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(
                route = Routes.REVIEW,
                arguments = listOf(navArgument("receiptId") { type = NavType.StringType }),
            ) {
                ReceiptReviewScreen(
                    onConfirmed = {
                        navController.navigate(Routes.HOME) {
                            popUpTo(Routes.HOME) { inclusive = true }
                        }
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(Routes.HISTORY) {
                HistoryScreen(
                    onOpenReceipt = { receiptId ->
                        navController.navigate(Routes.review(receiptId))
                    },
                    onBack = null,
                )
            }
            composable(Routes.PRODUCT_SEARCH) {
                ProductSearchScreen(
                    onOpenProduct = { productId ->
                        navController.navigate(Routes.productPrices(productId))
                    },
                    onBack = null,
                )
            }
            composable(
                route = Routes.PRODUCT_PRICES,
                arguments = listOf(navArgument("productId") { type = NavType.StringType }),
            ) {
                ProductPricesScreen(onBack = { navController.popBackStack() })
            }
        }
    }
}

@Composable
private fun LoggedInBottomBar(
    currentRoute: String?,
    onNavigate: (String) -> Unit,
) {
    val tabs = listOf(
        BottomTab(Routes.HOME, Icons.Default.Home, R.string.nav_home),
        BottomTab(Routes.HISTORY, Icons.AutoMirrored.Filled.ReceiptLong, R.string.nav_history),
        BottomTab(Routes.PRODUCT_SEARCH, Icons.Default.Search, R.string.nav_search),
    )
    NavigationBar {
        tabs.forEach { tab ->
            NavigationBarItem(
                selected = currentRoute == tab.route,
                onClick = { onNavigate(tab.route) },
                icon = { Icon(tab.icon, contentDescription = null) },
                label = { Text(stringResource(tab.labelRes)) },
            )
        }
    }
}

private fun NavHostController.navigateToTab(route: String) {
    navigate(route) {
        popUpTo(Routes.HOME) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
