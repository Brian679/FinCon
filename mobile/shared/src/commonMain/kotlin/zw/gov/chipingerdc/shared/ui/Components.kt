package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import zw.gov.chipingerdc.shared.sync.SyncState

private val Square = RoundedCornerShape(0.dp)
private val Radius4 = RoundedCornerShape(4.dp)

/** Draws a 1dp hairline along the bottom edge (Django admin table rows). */
fun Modifier.bottomRule(color: Color = CrdcColors.Hairline, width: Dp = 1.dp) = drawBehind {
    val y = size.height - width.toPx() / 2
    drawLine(color, Offset(0f, y), Offset(size.width, y), width.toPx())
}

/**
 * Screen frame in the Django-admin layout:
 *  header (site name in gold, user links) · breadcrumbs bar (with sync status) · page title · content.
 */
/** Height of the green header bar (below the status bar) and of the breadcrumb bar – the same on every screen and panel. */
val HEADER_HEIGHT = 56.dp
val CRUMBS_HEIGHT = 36.dp

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
    Column(Modifier.fillMaxSize().background(Color.White)) {
        // #header
        // Fixed heights so every header lines up – the menu panel beside (or over) a screen has its gold rule and
        // breadcrumb bar at exactly the same height as the screen, whether or not it shows the menu icon / profile picture.
        Row(
            Modifier.fillMaxWidth().background(CrdcColors.Green).statusBarsPadding().height(HEADER_HEIGHT).padding(start = 16.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LocalMenuOpener.current?.let { open ->
                // menu icon (three bars): opens the department menu
                Column(Modifier.clickable { open() }.padding(end = 14.dp, top = 4.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    repeat(3) { Box(Modifier.width(22.dp).height(2.dp).background(Color.White)) }
                }
            }
            Text(LocalSiteName.current, color = CrdcColors.Gold, fontSize = 19.sp, fontWeight = FontWeight.Light, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            actions()
            LocalProfile.current?.let { ProfileButton(it) }
        }
        Box(Modifier.fillMaxWidth().height(3.dp).background(CrdcColors.Gold))
        // div.breadcrumbs
        Row(
            Modifier.fillMaxWidth().background(CrdcColors.GreenDark).height(CRUMBS_HEIGHT).padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(if (onBack != null) "‹ Back" else "Home", color = Color.White, fontSize = 13.sp,
                modifier = if (onBack != null) Modifier.clickable { onBack() } else Modifier)
            if (onBack != null) {
                Text("  ›  $title", color = CrdcColors.BreadcrumbsText, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f))
            } else Spacer(Modifier.weight(1f))
            if (sync != null) SyncStatus(sync, pending, onSync)
        }
        if (sync?.online == false || sync?.needsLogin == true) {
            val text = if (sync.needsLogin) "Session expired – log in again to sync your work."
            else "You are offline. Showing data saved on this phone" + if (pending > 0) "; $pending change(s) will be sent when you reconnect." else "."
            Message(text, MessageKind.WARNING, Modifier.padding(start = 12.dp, end = 12.dp, top = 10.dp))
        }
        // h1 (light, quiet)
        Text(title, fontSize = 20.sp, fontWeight = FontWeight.Light, color = CrdcColors.Muted,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 14.dp, bottom = 4.dp), maxLines = 2, overflow = TextOverflow.Ellipsis)
        Column(Modifier.fillMaxSize(), content = content)
    }
}

@Composable
private fun SyncStatus(state: SyncState, pending: Long, onSync: (() -> Unit)?) {
    val text = when {
        state.running -> "Syncing…"
        state.online == false -> "Offline" + if (pending > 0) " · $pending waiting" else ""
        pending > 0 -> "$pending waiting · Sync"
        state.lastSync != null -> "Synced ${prettyDate(state.lastSync).takeLast(5)}"
        else -> "Sync"
    }
    Text(text, color = if (state.online == false || pending > 0) CrdcColors.Gold else CrdcColors.BreadcrumbsText, fontSize = 12.sp,
        modifier = if (onSync != null && !state.running) Modifier.clickable { onSync() } else Modifier)
}

/** Kept for callers that show sync status on their own. */
@Composable
fun SyncBar(state: SyncState, pending: Long, onSync: (() -> Unit)?) = SyncStatus(state, pending, onSync)

@Composable
fun ScrollColumn(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp), content = content)
}

@Composable
fun ListScreen(content: LazyListScope.() -> Unit) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp), content = content)
}

/** div.module with an <h2>/<caption> bar. */
@Composable
fun SectionCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().border(1.dp, CrdcColors.Hairline, Square).background(Color.White)) {
        if (title != null) Caption(title)
        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
    }
}

@Composable
fun Caption(title: String, color: Color = CrdcColors.Green) {
    Text(title.uppercase(), color = Color.White, fontSize = 12.sp, letterSpacing = 0.5.sp,
        modifier = Modifier.fillMaxWidth().background(color).padding(horizontal = 8.dp, vertical = 8.dp))
}

/** One row of a Django admin results table. */
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
    Row(
        Modifier.fillMaxWidth().background(Color.White).then(if (onClick != null) Modifier.clickable { onClick() } else Modifier)
            .bottomRule().padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, color = if (onClick != null) CrdcColors.Blue else CrdcColors.Body, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!subtitle.isNullOrBlank()) Text(subtitle, fontSize = 12.sp, color = CrdcColors.Muted, maxLines = 3, overflow = TextOverflow.Ellipsis,
                lineHeight = 16.sp)
            if (!note.isNullOrBlank()) Text(note, fontSize = 12.sp, color = CrdcColors.Warning)
        }
        Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 8.dp)) {
            if (trailing != null) Text(trailing, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CrdcColors.Body)
            if (status != null) StatusChip(status, statusCode ?: status)
        }
    }
}

private enum class Tone { GOOD, BAD, ATTENTION, NEUTRAL }

private fun tone(code: String): Tone = when (code.uppercase()) {
    "VALID", "PAID", "ISSUED", "APPROVED", "AUTHORISED", "VERIFIED", "RESOLVED", "CLOSED", "COMPLETED", "DONE", "ALLOCATED", "ACTIVE",
    "ORDERED", "INSPECTED", "RESPONDED", "GOOD" -> Tone.GOOD
    "VOIDED", "REJECTED", "FAILED", "CANCELLED", "EXPIRED", "URGENT", "CRITICAL", "QUERIED", "BROKEN", "RETURNED", "FINE" -> Tone.BAD
    "LOCAL", "SECONDARY", "SKIPPED", "WAITING" -> Tone.NEUTRAL
    else -> Tone.ATTENTION
}

fun statusColor(code: String): Color = when (tone(code)) {
    Tone.GOOD -> CrdcColors.Success
    Tone.BAD -> CrdcColors.Danger
    Tone.ATTENTION -> CrdcColors.Warning
    Tone.NEUTRAL -> CrdcColors.Muted
}

/** Status text with Django admin's yes / no / alert icon. */
@Composable
fun StatusChip(text: String, code: String = text) {
    // "Awaiting payment" (e.g. a licence) still needs something from the client: never show it as done
    val t = if (text.contains("awaiting", ignoreCase = true) || text.contains("unpaid", ignoreCase = true)) Tone.ATTENTION else tone(code)
    val icon = when (t) { Tone.GOOD -> "✔ "; Tone.BAD -> "✖ "; Tone.ATTENTION -> "⚠ "; Tone.NEUTRAL -> "" }
    val color = when (t) { Tone.GOOD -> CrdcColors.Success; Tone.BAD -> CrdcColors.Danger; Tone.ATTENTION -> CrdcColors.Warning; Tone.NEUTRAL -> CrdcColors.Muted }
    Text(icon + text, color = color, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
}

@Composable
fun KeyValue(label: String, value: String?) {
    Row(Modifier.fillMaxWidth().bottomRule().padding(vertical = 6.dp)) {
        Text("$label:", color = CrdcColors.Medium, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(130.dp))
        Text(value?.ifBlank { "—" } ?: "—", fontSize = 13.sp, color = CrdcColors.Body, modifier = Modifier.weight(1f))
    }
}

/** Flat summary box (top rule in the council colour). */
@Composable
fun Kpi(label: String, value: String, sub: String? = null, color: Color = CrdcColors.Green, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    val rule = when (color) { CrdcColors.Warning -> CrdcColors.Gold; else -> color }
    Column(
        modifier.border(1.dp, CrdcColors.Hairline, Square).background(Color.White)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
    ) {
        Box(Modifier.fillMaxWidth().height(3.dp).background(rule))
        Column(Modifier.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text(label.uppercase(), fontSize = 10.sp, letterSpacing = 0.3.sp, color = CrdcColors.Muted, maxLines = 2, lineHeight = 13.sp)
            Text(value, fontSize = if (value.length > 7) 16.sp else 21.sp, maxLines = 1, softWrap = false, color = if (color == CrdcColors.Danger) CrdcColors.Danger else CrdcColors.Body)
            if (sub != null) Text(sub, fontSize = 11.sp, color = CrdcColors.Muted, maxLines = 1)
        }
    }
}

/** Django admin form row: bold label, bordered input. */
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
    Column(modifier.fillMaxWidth()) {
        Text("$label:", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CrdcColors.Medium, modifier = Modifier.padding(bottom = 4.dp))
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = singleLine && minLines == 1,
            minLines = minLines,
            textStyle = TextStyle(fontSize = 15.sp, color = CrdcColors.Body),
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = when {
                password -> KeyboardType.Password
                number -> KeyboardType.Decimal
                else -> KeyboardType.Text
            }),
            decorationBox = { inner ->
                Box(Modifier.fillMaxWidth().heightIn(min = 40.dp).border(1.dp, if (error != null) CrdcColors.Danger else CrdcColors.Border, Radius4)
                    .background(Color.White, Radius4).padding(horizontal = 8.dp, vertical = 9.dp)) { inner() }
            },
        )
        if (error != null) Text(error, color = CrdcColors.Danger, fontSize = 12.sp)
    }
}

/** Select box. */
@Composable
fun <T> Picker(label: String, options: List<T>, selected: T?, toLabel: (T) -> String, onSelect: (T) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Column(modifier.fillMaxWidth()) {
        Text("$label:", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = CrdcColors.Medium, modifier = Modifier.padding(bottom = 4.dp))
        Box {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).border(1.dp, CrdcColors.Border, Radius4).clickable { open = true }
                    .padding(horizontal = 8.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(selected?.let(toLabel) ?: "---------", fontSize = 15.sp, color = CrdcColors.Body, modifier = Modifier.weight(1f),
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("▾", color = CrdcColors.Muted)
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { opt -> DropdownMenuItem(text = { Text(toLabel(opt)) }, onClick = { onSelect(opt); open = false }) }
            }
        }
    }
}

@Composable
fun ChoicePicker(label: String, choices: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) =
    Picker(label, choices, choices.firstOrNull { it.first == selected }, { it.second }, { onSelect(it.first) })

/** Square admin button. Danger -> red, Blue (secondary) -> grey, everything else -> council green. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, busy: Boolean = false, color: Color = CrdcColors.Green) {
    val bg = when (color) {
        CrdcColors.Danger -> CrdcColors.Danger
        CrdcColors.Blue -> CrdcColors.CloseButton
        else -> CrdcColors.Action
    }
    AdminButton(text, onClick, bg, enabled && !busy, busy, Modifier.fillMaxWidth())
}

@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier.fillMaxWidth()) =
    AdminButton(text, onClick, CrdcColors.CloseButton, true, false, modifier)

@Composable
fun AdminButton(text: String, onClick: () -> Unit, bg: Color, enabled: Boolean, busy: Boolean, modifier: Modifier) {
    Box(
        modifier.heightIn(min = 40.dp).background(if (enabled) bg else bg.copy(alpha = 0.45f), Radius4)
            .then(if (enabled) Modifier.clickable { onClick() } else Modifier).padding(horizontal = 15.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        if (busy) CircularProgressIndicator(Modifier.width(18.dp).height(18.dp), color = Color.White, strokeWidth = 2.dp)
        else Text(text, color = Color.White, fontSize = 14.sp)
    }
}

enum class MessageKind { SUCCESS, WARNING, ERROR, INFO }

/** ul.messagelist li */
@Composable
fun Message(text: String, kind: MessageKind, modifier: Modifier = Modifier) {
    val (bg, icon, iconColor) = when (kind) {
        MessageKind.SUCCESS -> Triple(CrdcColors.MsgSuccess, "✔", CrdcColors.Success)
        MessageKind.WARNING -> Triple(CrdcColors.MsgWarning, "⚠", CrdcColors.Warning)
        MessageKind.ERROR -> Triple(CrdcColors.MsgError, "✖", CrdcColors.Danger)
        MessageKind.INFO -> Triple(CrdcColors.MsgInfo, "ℹ", CrdcColors.Blue)
    }
    Row(modifier.fillMaxWidth().background(bg).padding(horizontal = 10.dp, vertical = 9.dp)) {
        Text(icon, color = iconColor, fontSize = 13.sp, modifier = Modifier.padding(end = 8.dp))
        Text(text, color = CrdcColors.Body, fontSize = 13.sp)
    }
}

@Composable
fun InfoBox(text: String, color: Color = CrdcColors.Blue) = Message(text, when (color) {
    CrdcColors.Danger -> MessageKind.ERROR
    CrdcColors.Warning, CrdcColors.Gold -> MessageKind.WARNING
    CrdcColors.Success, CrdcColors.Green -> MessageKind.SUCCESS
    else -> MessageKind.INFO
})

@Composable
fun Empty(text: String) {
    Text(text, color = CrdcColors.Muted, fontSize = 13.sp, modifier = Modifier.fillMaxWidth().bottomRule().padding(8.dp))
}

@Composable
fun Progress(percent: Int) {
    LinearProgressIndicator(progress = { percent.coerceIn(0, 100) / 100f }, modifier = Modifier.fillMaxWidth().height(6.dp),
        color = CrdcColors.Green, trackColor = CrdcColors.Hairline)
}

@Composable
fun Divider() = HorizontalDivider(Modifier.padding(vertical = 4.dp), color = CrdcColors.Hairline)

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

/** Approve / reject panel (submit-row with a default and a delete-style button). */
@Composable
fun DecisionPanel(title: String, approveText: String = "Approve", rejectText: String = "Reject", onDecide: (approve: Boolean, comment: String) -> Unit) {
    var comment by remember { mutableStateOf("") }
    SectionCard(title) {
        Field("Comment", comment, { comment = it }, singleLine = false, minLines = 2)
        SubmitRow {
            AdminButton(approveText, { onDecide(true, comment) }, CrdcColors.Action, true, false, Modifier.weight(1f))
            AdminButton(rejectText, { onDecide(false, comment) }, CrdcColors.Danger, true, false, Modifier.weight(1f))
        }
        Text("Decisions are queued if you are offline and applied when the phone syncs. Segregation-of-duties rules are checked by the server.",
            fontSize = 11.sp, color = CrdcColors.Muted)
    }
}

/** div.submit-row */
@Composable
fun SubmitRow(content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit) {
    Row(Modifier.fillMaxWidth().background(CrdcColors.Darkened).border(1.dp, CrdcColors.Hairline).padding(8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp), content = content)
}

/** Django admin index: a module whose rows are links with optional count and "+ Add" link. */
data class IndexRow(val label: String, val count: Int = 0, val onOpen: () -> Unit, val onAdd: (() -> Unit)? = null)

@Composable
fun IndexModule(title: String, rows: List<IndexRow>) {
    Column(Modifier.fillMaxWidth().border(1.dp, CrdcColors.Hairline, Square)) {
        Caption(title)
        rows.forEachIndexed { i, r ->
            Row(
                Modifier.fillMaxWidth().background(if (i % 2 == 1) CrdcColors.Darkened else Color.White).bottomRule()
                    .padding(horizontal = 10.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(r.label + if (r.count > 0) " (${r.count})" else "", color = CrdcColors.Blue, fontSize = 15.sp,
                    modifier = Modifier.weight(1f).clickable { r.onOpen() })
                if (r.onAdd != null) Text("✚ Add", color = CrdcColors.Green, fontSize = 13.sp, modifier = Modifier.clickable { r.onAdd.invoke() })
            }
        }
    }
}

/** When set (phones), the header shows a menu icon that calls it. */
val LocalMenuOpener = androidx.compose.runtime.staticCompositionLocalOf<(() -> Unit)?> { null }

/** Simple back-stack navigator shared by both apps. */
class Navigator<S>(start: S) {
    private val stack = androidx.compose.runtime.mutableStateListOf(start)
    val current: S get() = stack.last()
    val canGoBack: Boolean get() = stack.size > 1
    fun push(screen: S) { stack.add(screen) }
    fun pop() { if (stack.size > 1) stack.removeAt(stack.lastIndex) }
    fun replaceAll(screen: S) { stack.clear(); stack.add(screen) }
}

/** One input in an [ActionPanel]. kind: text, number, multiline, choice. */
data class FieldSpec(val key: String, val label: String, val kind: String = "text", val choices: List<Pair<String, String>> = emptyList(), val initial: String = "")

private val NEGATIVE_ACTIONS = setOf("reject", "return", "fail", "cancel")

/** A small form with stage buttons (recommend / approve / reject …) in a submit row. */
@Composable
fun ActionPanel(title: String, fields: List<FieldSpec>, buttons: List<Pair<String, String>>, note: String? = null,
                onAction: (action: String, values: Map<String, String>) -> Unit) {
    val values = remember(title) { mutableStateMapOf<String, String>().apply { fields.forEach { put(it.key, it.initial.ifBlank { it.choices.firstOrNull()?.first ?: "" }) } } }
    SectionCard(title) {
        fields.forEach { f ->
            when (f.kind) {
                "choice" -> ChoicePicker(f.label, f.choices, values[f.key] ?: "") { values[f.key] = it }
                "multiline" -> Field(f.label, values[f.key] ?: "", { values[f.key] = it }, singleLine = false, minLines = 3)
                "number" -> Field(f.label, values[f.key] ?: "", { values[f.key] = it }, number = true)
                else -> Field(f.label, values[f.key] ?: "", { values[f.key] = it })
            }
        }
        Column(Modifier.fillMaxWidth().background(CrdcColors.Darkened).border(1.dp, CrdcColors.Hairline).padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            buttons.forEachIndexed { i, (action, label) ->
                val bg = when {
                    action in NEGATIVE_ACTIONS -> CrdcColors.Danger
                    i == 0 -> CrdcColors.Action
                    else -> CrdcColors.ActionLight
                }
                AdminButton(label, { onAction(action, values.toMap()) }, bg, true, false, Modifier.fillMaxWidth())
            }
        }
        if (note != null) Text(note, fontSize = 11.sp, color = CrdcColors.Muted)
    }
}
