package no.prislapp.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val displayDateFormatter = DateTimeFormatter.ofPattern("dd.MM.yyyy")
private val osloZone = ZoneId.of("Europe/Oslo")

fun formatReceiptSubtitle(purchaseDateIso: String?, total: BigDecimal?): String {
    val dateText = purchaseDateIso?.let(::formatPurchaseDate)
    val totalText = total?.let { "${it.toPlainString().replace('.', ',')} kr" }
    return listOfNotNull(dateText, totalText).joinToString(" · ")
}

private fun formatPurchaseDate(purchaseDateIso: String): String? {
    return runCatching {
        val localDate = if (purchaseDateIso.length == 10) {
            LocalDate.parse(purchaseDateIso)
        } else {
            OffsetDateTime.parse(purchaseDateIso).atZoneSameInstant(osloZone).toLocalDate()
        }
        localDate.format(displayDateFormatter)
    }.getOrNull()
}

@Composable
fun ReceiptRow(
    title: String,
    subtitle: String,
    statusLabel: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Column(modifier = modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onClick)
                .padding(PaddingValues(vertical = 12.dp)),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                )
                if (subtitle.isNotBlank()) {
                    Text(
                        text = subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (!statusLabel.isNullOrBlank()) {
                Text(
                    text = statusLabel,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        if (actionLabel != null && onAction != null) {
            TextButton(
                onClick = onAction,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
            ) {
                Text(actionLabel)
            }
        }
        HorizontalDivider()
    }
}
