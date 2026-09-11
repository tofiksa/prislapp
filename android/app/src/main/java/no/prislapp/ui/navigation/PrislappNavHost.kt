package no.prislapp.ui.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
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
import no.prislapp.ui.home.ReceiptsScreen
import no.prislapp.ui.product.ProductPricesScreen
import no.prislapp.ui.product.ProductSearchScreen
import no.prislapp.ui.receipt.ReceiptProcessingScreen
import no.prislapp.ui.receipt.ReceiptReviewScreen
import no.prislapp.ui.shoppinglist.ShoppingListScreen

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

    if (!uiState.isAuthResolved) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator()
        }
        return
    }

    LaunchedEffect(uiState.isLoggedIn) {
        if (uiState.isLoggedIn) {
            navController.navigate(Routes.LOGGED_IN_START) {
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
            startDestination = if (uiState.isLoggedIn) Routes.LOGGED_IN_START else Routes.LOGIN,
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
            composable(Routes.SHOPPING_LIST) { entry ->
                val ctaCount by entry.savedStateHandle
                    .getStateFlow("firstReceiptReadyCount", 0)
                    .collectAsStateWithLifecycle()
                ShoppingListScreen(
                    firstReceiptReadyCount = ctaCount.takeIf { it > 0 },
                    onLogout = { authViewModel.logout() },
                )
            }
            composable(Routes.RECEIPTS) {
                ReceiptsScreen(
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
                        navController.navigate(Routes.processing(localId))
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
                        navController.navigate(Routes.review(receiptId))
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable(
                route = Routes.REVIEW,
                arguments = listOf(navArgument("receiptId") { type = NavType.StringType }),
            ) {
                ReceiptReviewScreen(
                    onConfirmed = { readyCount ->
                        navController.navigate(Routes.SHOPPING_LIST) {
                            popUpTo(Routes.SHOPPING_LIST) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                        runCatching {
                            navController.getBackStackEntry(Routes.SHOPPING_LIST)
                                .savedStateHandle["firstReceiptReadyCount"] = readyCount
                        }
                    },
                    onBack = { navController.popBackStack() },
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
        BottomTab(Routes.SHOPPING_LIST, Icons.Default.ShoppingCart, R.string.nav_shopping_list),
        BottomTab(Routes.PRODUCT_SEARCH, Icons.Default.Search, R.string.nav_products),
        BottomTab(Routes.RECEIPTS, Icons.AutoMirrored.Filled.ReceiptLong, R.string.nav_receipts),
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
        popUpTo(Routes.SHOPPING_LIST) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
