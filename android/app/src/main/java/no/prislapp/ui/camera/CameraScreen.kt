package no.prislapp.ui.camera

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.automirrored.filled.RotateRight
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.SubcomposeAsyncImage
import kotlinx.coroutines.suspendCancellableCoroutine
import no.prislapp.R
import no.prislapp.ui.components.PrislappTopBar
import java.io.File
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

@Composable
fun CameraScreen(
    onCaptured: (localId: Long) -> Unit,
    onBack: () -> Unit,
    viewModel: CameraViewModel = hiltViewModel(),
) {
    val context = LocalContext.current
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        hasCameraPermission = granted
    }
    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        uri?.let(viewModel::onGalleryImageSelected)
    }
    val openGallery = {
        galleryLauncher.launch(
            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
        )
    }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    LaunchedEffect(uiState.savedLocalId) {
        val localId = uiState.savedLocalId ?: return@LaunchedEffect
        onCaptured(localId)
    }

    Scaffold(
        topBar = {
            PrislappTopBar(
                title = stringResource(R.string.camera_title),
                onBack = onBack,
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            val previewFile = uiState.previewFile
            when {
                uiState.isSaving -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }
                previewFile != null -> {
                    ReceiptPreviewContent(
                        previewFile = previewFile,
                        rotationDegrees = uiState.rotationDegrees,
                        onUse = viewModel::acceptPreview,
                        onRetake = viewModel::retake,
                        onRotate = viewModel::rotatePreview,
                    )
                }
                hasCameraPermission -> {
                    CameraPreviewContent(
                        onCapture = viewModel::onPhotoCaptured,
                        createOutputFile = viewModel::createOutputFile,
                        onError = viewModel::onCaptureError,
                    )
                }
                else -> {
                    CameraPermissionDeniedContent(
                        onRequestPermission = { permissionLauncher.launch(Manifest.permission.CAMERA) },
                        onPickGallery = openGallery,
                    )
                }
            }

            if (!uiState.isSaving && previewFile == null && hasCameraPermission) {
                IconButton(
                    onClick = openGallery,
                    modifier = Modifier
                        .align(Alignment.BottomStart)
                        .padding(24.dp)
                        .size(48.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.PhotoLibrary,
                        contentDescription = stringResource(R.string.pick_from_gallery),
                    )
                }
            }

            val errorText = uiState.errorResId?.let { stringResource(it) } ?: uiState.error
            errorText?.let { error ->
                Text(
                    text = error,
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(16.dp),
                )
            }
        }
    }
}

@Composable
private fun CameraPermissionDeniedContent(
    onRequestPermission: () -> Unit,
    onPickGallery: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(text = stringResource(R.string.camera_permission_denied_gallery_ok))
        Spacer(modifier = Modifier.height(16.dp))
        Button(
            onClick = onRequestPermission,
            modifier = Modifier.height(48.dp),
        ) {
            Text(stringResource(R.string.camera_permission))
        }
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedButton(
            onClick = onPickGallery,
            modifier = Modifier.height(48.dp),
        ) {
            Text(stringResource(R.string.pick_from_gallery))
        }
    }
}

@Composable
private fun ReceiptPreviewContent(
    previewFile: File,
    rotationDegrees: Int,
    onUse: () -> Unit,
    onRetake: () -> Unit,
    onRotate: () -> Unit,
) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    Box(modifier = Modifier.fillMaxSize()) {
        SubcomposeAsyncImage(
            model = previewFile,
            contentDescription = stringResource(R.string.receipt_preview_zoom),
            contentScale = ContentScale.Fit,
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                    rotationZ = rotationDegrees.toFloat()
                    translationX = offset.x
                    translationY = offset.y
                }
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, zoom, _ ->
                        scale = (scale * zoom).coerceIn(1f, 8f)
                        offset += pan
                    }
                },
        )
        Row(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedButton(
                onClick = onRetake,
                modifier = Modifier
                    .height(48.dp)
                    .weight(1f),
            ) {
                Text(stringResource(R.string.receipt_preview_retake))
            }
            FilledIconButton(
                onClick = onRotate,
                modifier = Modifier.size(48.dp),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.RotateRight,
                    contentDescription = stringResource(R.string.receipt_preview_rotate),
                )
            }
            Button(
                onClick = onUse,
                modifier = Modifier
                    .height(48.dp)
                    .weight(1f),
            ) {
                Text(stringResource(R.string.receipt_preview_use_image))
            }
        }
    }
}

@Composable
private fun CameraPreviewContent(
    onCapture: (File) -> Unit,
    createOutputFile: () -> File,
    onError: (String) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember {
        PreviewView(context).apply {
            // Samsung Galaxy devices (e.g. S21) can render a black preview with the default mode.
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        }
    }
    val imageCapture = remember { ImageCapture.Builder().build() }
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    var provider by remember { mutableStateOf<ProcessCameraProvider?>(null) }
    var capturing by remember { mutableStateOf(false) }
    DisposableEffect(Unit) {
        onDispose { provider?.unbindAll(); cameraExecutor.shutdown() }
    }

    LaunchedEffect(previewView) {
        try {
        val cameraProvider = suspendCancellableCoroutine { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener(
                {
                    try {
                        cont.resume(future.get())
                    } catch (e: Exception) {
                        cont.resumeWithException(e)
                    }
                },
                ContextCompat.getMainExecutor(context),
            )
        }
        val preview = Preview.Builder().build().also {
            it.surfaceProvider = previewView.surfaceProvider
        }
        cameraProvider.unbindAll()
        provider = cameraProvider
        cameraProvider.bindToLifecycle(
            lifecycleOwner,
            CameraSelector.DEFAULT_BACK_CAMERA,
            preview,
            imageCapture,
        )
        } catch (e: kotlinx.coroutines.CancellationException) { throw e
        } catch (e: Exception) { onError(e.message ?: "Kunne ikke starte kamera") }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            factory = { previewView },
            modifier = Modifier.fillMaxSize(),
        )
        Text(
            text = stringResource(R.string.camera_guidance),
            color = Color.White,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(16.dp),
        )
        FilledIconButton(
            enabled = !capturing && provider != null,
            onClick = {
                capturing = true
                val outputFile = createOutputFile()
                val outputOptions = ImageCapture.OutputFileOptions.Builder(outputFile).build()
                imageCapture.takePicture(
                    outputOptions,
                    cameraExecutor,
                    object : ImageCapture.OnImageSavedCallback {
                        override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                            ContextCompat.getMainExecutor(context).execute { capturing = false; onCapture(outputFile) }
                        }

                        override fun onError(exception: ImageCaptureException) {
                            outputFile.delete()
                            ContextCompat.getMainExecutor(context).execute {
                                capturing = false
                                onError(exception.message ?: "Kunne ikke ta bilde")
                            }
                        }
                    },
                )
            },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(24.dp)
                .size(72.dp),
        ) {
            Icon(
                imageVector = Icons.Default.CameraAlt,
                contentDescription = stringResource(R.string.capture_button),
                tint = Color.White,
            )
        }
    }
}
