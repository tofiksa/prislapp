package no.prislapp.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import no.prislapp.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(onLogout: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.home_title)) })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
        ) {
            Text(text = stringResource(R.string.welcome))

            OutlinedButton(
                onClick = {},
                enabled = false,
                modifier = Modifier.padding(top = 16.dp),
            ) {
                Text(stringResource(R.string.capture_receipt_soon))
            }

            Button(
                onClick = onLogout,
                modifier = Modifier.padding(top = 24.dp),
            ) {
                Text(stringResource(R.string.logout))
            }
        }
    }
}
