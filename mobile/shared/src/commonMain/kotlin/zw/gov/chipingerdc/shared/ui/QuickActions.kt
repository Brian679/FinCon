package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** One big, thumb-friendly shortcut: a symbol in a coloured circle, a short label and an optional count. */
data class QuickAction(val symbol: String, val label: String, val color: Color = CrdcColors.Green, val badge: Int = 0, val onClick: () -> Unit)

/**
 * The things people do most, as a grid of large tiles at the top of a dashboard – one tap instead of
 * opening the menu. Three tiles a row on a phone, more on a tablet or desktop.
 */
@Composable
fun QuickActions(title: String, actions: List<QuickAction>) {
    if (actions.isEmpty()) return
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title.uppercase(), fontSize = 11.sp, letterSpacing = 0.5.sp, color = CrdcColors.Muted, fontWeight = FontWeight.SemiBold)
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val perRow = when {
                maxWidth > 900.dp -> 6
                maxWidth > 560.dp -> 4
                else -> 3
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                actions.chunked(perRow).forEach { row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        row.forEach { a -> Tile(a, Modifier.weight(1f)) }
                        repeat(perRow - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun Tile(a: QuickAction, modifier: Modifier) {
    Column(
        modifier.border(1.dp, CrdcColors.Hairline, RoundedCornerShape(10.dp)).background(Color.White, RoundedCornerShape(10.dp))
            .clickable { a.onClick() }.padding(vertical = 12.dp, horizontal = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Box(Modifier.size(44.dp).background(a.color.copy(alpha = 0.12f), CircleShape), contentAlignment = Alignment.Center) {
                Text(a.symbol, fontSize = 20.sp, color = a.color, fontWeight = FontWeight.Bold)
            }
            if (a.badge > 0) Box(Modifier.align(Alignment.TopEnd).padding(start = 30.dp).background(CrdcColors.Danger, CircleShape)
                .padding(horizontal = 6.dp, vertical = 1.dp)) {
                Text(if (a.badge > 99) "99+" else a.badge.toString(), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(a.label, fontSize = 12.sp, lineHeight = 15.sp, textAlign = TextAlign.Center, color = CrdcColors.Body, maxLines = 2)
    }
}

/** Friendly empty state: a symbol, what this list is for, and the next thing to do. */
@Composable
fun EmptyState(symbol: String, title: String, hint: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().padding(vertical = 28.dp, horizontal = 16.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(64.dp).background(CrdcColors.Green.copy(alpha = 0.08f), CircleShape), contentAlignment = Alignment.Center) {
            Text(symbol, fontSize = 28.sp, color = CrdcColors.Green)
        }
        Text(title, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = CrdcColors.Body, textAlign = TextAlign.Center)
        Text(hint, fontSize = 13.sp, color = CrdcColors.Muted, textAlign = TextAlign.Center)
        if (actionLabel != null && onAction != null) PrimaryButton(actionLabel, onClick = onAction)
    }
}

/** A short greeting line for the top of a dashboard: "Good morning, Chipo" + today's date. */
fun greeting(hour: Int, firstName: String): String {
    val part = when (hour) { in 5..11 -> "Good morning"; in 12..16 -> "Good afternoon"; else -> "Good evening" }
    return if (firstName.isBlank()) part else "$part, $firstName"
}
