package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Empty list, Django admin style: a quiet line of text and, if useful, the next action as a plain button. */
@Composable
fun EmptyState(title: String, hint: String, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 12.dp)) {
        Text(title, fontSize = 13.sp, color = CrdcColors.Muted)
        Text(hint, fontSize = 12.sp, color = CrdcColors.Muted)
        if (actionLabel != null && onAction != null) PrimaryButton(actionLabel, onClick = onAction)
    }
}
