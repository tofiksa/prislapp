package no.prislapp.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
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

@Composable
fun PrislappNavHost(
    authViewModel: AuthViewModel = hiltViewModel(),
) {
    val navController = rememberNavController()
    val uiState by authViewModel.uiState.collectAsStateWithLifecycle()

    LaunchedEffect(uiState.isLoggedIn) {
        if (uiState.isLoggedIn) {
            navController.navigate(Routes.HOME) {
                popUpTo(Routes.LOGIN) { inclusive = true }
            }
        } else {
            navController.navigate(Routes.LOGIN) {
                popUpTo(Routes.HOME) { inclusive = true }
            }
        }
    }

    NavHost(
        navController = navController,
        startDestination = Routes.LOGIN,
    ) {
        composable(Routes.LOGIN) {
            LoginScreen(
                viewModel = authViewModel,
                onNavigateToRegister = { navController.navigate(Routes.REGISTER) },
                onLoggedIn = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
            )
        }
        composable(Routes.REGISTER) {
            RegisterScreen(
                viewModel = authViewModel,
                onNavigateToLogin = { navController.popBackStack() },
                onRegistered = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
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
                onOpenHistory = { navController.navigate(Routes.HISTORY) },
                onOpenProductSearch = { navController.navigate(Routes.PRODUCT_SEARCH) },
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
                onBack = { navController.popBackStack() },
            )
        }
        composable(Routes.PRODUCT_SEARCH) {
            ProductSearchScreen(
                onOpenProduct = { productId ->
                    navController.navigate(Routes.productPrices(productId))
                },
                onBack = { navController.popBackStack() },
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
