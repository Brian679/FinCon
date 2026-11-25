package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import zw.gov.chipingerdc.shared.sync.SyncState

@Composable
fun AppScreen(
    title: String,
    onBack: (() -> Unit)? = null,
    sync: SyncState? = null,
    pending: Long = 0,
    onSync: (() -> Unit)? = null,
    actions: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    navigationIcon = {
                        if (onBack != null) TextButton(onClick = onBack) { Text("‹ Back", color = Color.White) }
                    },
                    actions = { actions() },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = CrdcColors.Green, titleContentColor = Color.White, actionIconContentColor = Color.White,
                    ),
                )
                if (sync != null) SyncBar(sync, pending, onSync)
            }
        },
        containerColor = CrdcColors.Background,
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize(), content = content)
    }
}

@Composable
fun SyncBar(state: SyncState, pending: Long, onSync: (() -> Unit)?) {
    val (bg, text) = when {
        state.running -> CrdcColors.Blue to "Syncing…"
        state.needsLogin -> CrdcColors.Danger to "Session expired – log in again to sync"
        state.online == false -> CrdcColors.Warning to if (pending > 0) "Offline · $pending change(s) waiting to sync" else "Offline · showing saved data"
        pending > 0 -> CrdcColors.Blue to "$pending change(s) waiting to sync"
        else -> CrdcColors.GreenDark to ("Up to date" + (state.lastSync?.let { " · ${prettyDate(it)}" } ?: ""))
    }
    Row(
        Modifier.fillMaxWidth().background(bg).clickable(enabled = onSync != null && !state.running) { onSync?.invoke() }.padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, color = Color.White, fontSize = 12.sp, modifier = Modifier.weight(1f))
        if (onSync != null && !state.running) Text("Sync now ⟳", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun ScrollColumn(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
}

@Composable
fun ListScreen(content: LazyListScope.() -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
}

@Composable
fun SectionCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color.White), elevation = CardDefaults.cardElevation(1.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (title != null) Text(title, style = MaterialTheme.typography.titleSmall, color = CrdcColors.GreenDark, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
fun RowCard(
    title: String,
    subtitle: String? = null,
    trailing: String? = null,
    status: String? = null,
    statusCode: String? = null,
    note: String? = null,
    onClick: (() -> Unit)? = null,
) {
    Card(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(1.dp),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (!subtitle.isNullOrBlank()) Text(subtitle, fontSize = 13.sp, color = CrdcColors.Muted, maxLines = 3, overflow = TextOverflow.Ellipsis)
                if (!note.isNullOrBlank()) Text("⏳ $note", fontSize = 12.sp, color = CrdcColors.Blue)
            }
            Column(horizontalAlignment = Alignment.End) {
                if (trailing != null) Text(trailing, fontWeight = FontWeight.Bold)
                if (status != null) StatusChip(status, statusCode ?: status)
            }
        }
    }
}

fun statusColor(code: String): Color = when (code.uppercase()) {
    "VALID", "PAID", "ISSUED", "APPROVED", "AUTHORISED", "VERIFIED", "RESOLVED", "CLOSED", "COMPLETED", "DONE", "ALLOCATED", "ACTIVE",
    "ORDERED", "INSPECTED", "RESPONDED" -> CrdcColors.Success
    "VOIDED", "REJECTED", "FAILED", "CANCELLED", "EXPIRED", "URGENT", "CRITICAL", "QUERIED" -> CrdcColors.Danger
    "PENDING", "LOCAL" -> CrdcColors.Blue
    else -> CrdcColors.Warning
}

@Composable
fun StatusChip(text: String, code: String = text) {
    Box(Modifier.background(statusColor(code), RoundedCornerShape(50)).padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(text, color = Color.White, fontSize = 11.sp, maxLines = 1)
    }
}

@Composable
fun KeyValue(label: String, value: String?) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(label, color = CrdcColors.Muted, fontSize = 13.sp, modifier = Modifier.width(130.dp))
        Text(value?.ifBlank { "—" } ?: "—", fontSize = 14.sp, modifier = Modifier.weight(1f))
    }
}

@Composable
fun Kpi(label: String, value: String, sub: String? = null, color: Color = CrdcColors.Green, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    Card(
        modifier.then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        colors = CardDefaults.cardColors(containerColor = Color.White), elevation = CardDefaults.cardElevation(1.dp),
    ) {
        Row {
            Box(Modifier.width(4.dp).height(72.dp).background(color))
            Column(Modifier.padding(10.dp)) {
                Text(label, fontSize = 12.sp, color = CrdcColors.Muted, maxLines = 2)
                Text(value, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                if (sub != null) Text(sub, fontSize = 11.sp, color = CrdcColors.Muted, maxLines = 1)
            }
        }
    }
}

@Composable
fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    number: Boolean = false,
    password: Boolean = false,
    singleLine: Boolean = true,
    minLines: Int = 1,
    error: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        modifier = modifier.fillMaxWidth(),
        singleLine = singleLine && minLines == 1,
        minLines = minLines,
        isError = error != null,
        supportingText = error?.let { { Text(it) } },
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = when {
            password -> KeyboardType.Password
            number -> KeyboardType.Decimal
            else -> KeyboardType.Text
        }),
    )
}

/** A simple, stable dropdown: button + menu. */
@Composable
fun <T> Picker(label: String, options: List<T>, selected: T?, toLabel: (T) -> String, onSelect: (T) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Column(modifier.fillMaxWidth()) {
        Text(label, fontSize = 12.sp, color = CrdcColors.Muted)
        Box {
            OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
                Text(selected?.let(toLabel) ?: "Select…", modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("▾")
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { opt ->
                    DropdownMenuItem(text = { Text(toLabel(opt)) }, onClick = { onSelect(opt); open = false })
                }
            }
        }
    }
}

@Composable
fun ChoicePicker(label: String, choices: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) =
    Picker(label, choices, choices.firstOrNull { it.first == selected }, { it.second }, { onSelect(it.first) })

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, busy: Boolean = false, color: Color = CrdcColors.Green) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = Modifier.fillMaxWidth().height(48.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color)) {
        if (busy) CircularProgressIndicator(Modifier.width(20.dp).height(20.dp), color = Color.White, strokeWidth = 2.dp) else Text(text)
    }
}

@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier.fillMaxWidth()) {
    OutlinedButton(onClick = onClick, modifier = modifier) { Text(text) }
}

@Composable
fun InfoBox(text: String, color: Color = CrdcColors.Blue) {
    Box(Modifier.fillMaxWidth().background(color.copy(alpha = 0.1f), RoundedCornerShape(8.dp)).padding(12.dp)) {
        Text(text, color = color, fontSize = 13.sp)
    }
}

@Composable
fun Empty(text: String) {
    Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { Text(text, color = CrdcColors.Muted) }
}

@Composable
fun Progress(percent: Int) {
    LinearProgressIndicator(progress = { percent.coerceIn(0, 100) / 100f }, modifier = Modifier.fillMaxWidth().height(6.dp), color = CrdcColors.Success)
}

@Composable
fun Divider() = HorizontalDivider(Modifier.padding(vertical = 4.dp))

@Composable
fun Gap(h: Int = 8) = Spacer(Modifier.height(h.dp))

@Composable
fun ConfirmDialog(title: String, text: String, confirm: String = "Confirm", onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = { onConfirm(); onDismiss() }) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** Decision panel used for approvals: comment box + approve / reject. */
@Composable
fun DecisionPanel(title: String, approveText: String = "Approve", rejectText: String = "Reject", onDecide: (approve: Boolean, comment: String) -> Unit) {
    var comment by remember { mutableStateOf("") }
    SectionCard(title) {
        Field("Comment", comment, { comment = it }, singleLine = false, minLines = 2)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onDecide(true, comment) }, colors = ButtonDefaults.buttonColors(containerColor = CrdcColors.Success), modifier = Modifier.weight(1f)) { Text(approveText) }
            OutlinedButton(onClick = { onDecide(false, comment) }, modifier = Modifier.weight(1f)) { Text(rejectText, color = CrdcColors.Danger) }
        }
        Text("Decisions are queued if you are offline and applied when the phone syncs. Segregation-of-duties rules are checked by the server.",
            fontSize = 11.sp, color = CrdcColors.Muted)
    }
}

/** Simple back-stack navigator shared by both apps. */
class Navigator<S>(start: S) {
    private val stack = androidx.compose.runtime.mutableStateListOf(start)
    val current: S get() = stack.last()
    val canGoBack: Boolean get() = stack.size > 1
    fun push(screen: S) { stack.add(screen) }
    fun pop() { if (stack.size > 1) stack.removeAt(stack.lastIndex) }
    fun replaceAll(screen: S) { stack.clear(); stack.add(screen) }
}
