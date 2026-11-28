package zw.gov.chipingerdc.council

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.PickedFile
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Correspondence
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.FileInfo
import zw.gov.chipingerdc.shared.model.PhoneMessage
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.rememberCameraCapture
import zw.gov.chipingerdc.shared.rememberFilePicker
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.bottomRule
import zw.gov.chipingerdc.shared.ui.prettyDate

private const val OFFLINE = "No connection. Try again when you are online."

val FILE_KINDS = listOf("SCAN" to "Scanned letter", "QUOTE" to "Quotation", "INVOICE" to "Invoice", "DELIVERY" to "Delivery note",
    "EVIDENCE" to "Supporting document", "PHOTO" to "Photo", "OTHER" to "Other")

/** Send a picked / photographed file to the server, attached to a request ("funds") or a letter ("correspondence"). */
suspend fun uploadAttachment(sdk: CouncilSdk, targetType: String, targetId: String, kind: String, file: PickedFile) {
    sdk.uploadFile("attachments/", "file", file.name, file.bytes, file.mime, mapOf("target_type" to targetType, "target_id" to targetId, "kind" to kind))
}

fun sizeLabel(bytes: Long) = when {
    bytes >= 1_048_576 -> "${(bytes * 10 / 1_048_576) / 10.0} MB"
    bytes >= 1024 -> "${bytes / 1024} KB"
    else -> "$bytes B"
}

/** Files on a request or a letter: open (one-hour link), photograph a document or attach a file. */
@Composable
fun FilesCard(sdk: CouncilSdk, targetType: String, targetId: String, files: List<FileInfo>, canAttach: Boolean, defaultKind: String,
              title: String = "Files") {
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    var kind by remember(targetId, defaultKind) { mutableStateOf(defaultKind) }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    fun send(f: PickedFile?) {
        if (f == null) return
        busy = true
        scope.launch {
            runCatching { uploadAttachment(sdk, targetType, targetId, kind, f); sdk.sync.sync() }
                .onSuccess { msg = "${f.name} attached." to true }.onFailure { msg = (it.message ?: OFFLINE) to false }
            busy = false
        }
    }
    val camera = rememberCameraCapture { send(it) }
    val picker = rememberFilePicker { send(it) }
    SectionCard(title) {
        if (files.isEmpty()) Empty(if (targetType == "correspondence") "No scan." else "No files.")
        files.forEach { f ->
            Column(Modifier.fillMaxWidth().bottomRule().clickable {
                scope.launch {
                    runCatching { sdk.postJson("attachments/${f.id}/link/", buildJsonObject { }) }
                        .onSuccess { r -> (r["url"] as? JsonPrimitive)?.content?.let { uri.openUri(it) } }
                        .onFailure { msg = (it.message ?: OFFLINE) to false }
                }
            }.padding(vertical = 8.dp)) {
                Text(f.name, fontSize = 14.sp, color = CrdcColors.Blue, fontWeight = FontWeight.SemiBold)
                Text("${f.kindLabel} · ${sizeLabel(f.size)} · ${f.uploadedByName} · ${prettyDate(f.createdAt)}", fontSize = 12.sp, color = CrdcColors.Muted)
            }
        }
        msg?.let { InfoBox(it.first, if (it.second) CrdcColors.Success else CrdcColors.Danger) }
        if (canAttach) {
            if (targetType != "correspondence") ChoicePicker("Type of file", FILE_KINDS, kind) { kind = it }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { PrimaryButton("Scan with camera", onClick = { camera() }, busy = busy) }
                androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { SecondaryButton("Attach file", { picker() }) }
            }
        }
    }
}

/** Files chosen on a form before the record exists on the server; they are sent after it syncs. */
@Composable
fun PendingFiles(files: MutableList<PickedFile>, label: String) {
    val camera = rememberCameraCapture { f -> if (f != null) files.add(f) }
    val picker = rememberFilePicker { f -> if (f != null) files.add(f) }
    SectionCard(label) {
        if (files.isEmpty()) Empty("No files.")
        files.toList().forEachIndexed { i, f ->
            Row(Modifier.fillMaxWidth().bottomRule().padding(vertical = 6.dp)) {
                Text(f.name, Modifier.weight(1f), fontSize = 14.sp)
                Text("${sizeLabel(f.bytes.size.toLong())}   Remove", fontSize = 12.sp, color = CrdcColors.Danger, modifier = Modifier.clickable { files.removeAt(i) })
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { PrimaryButton("Scan with camera", onClick = { camera() }) }
            androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { SecondaryButton("Attach file", { picker() }) }
        }
    }
}

fun staffChoices(staff: List<StaffMember>, exclude: Long? = null): List<Pair<String, String>> =
    staff.filter { it.isActive && it.userId != exclude }.sortedBy { it.fullName }
        .map { it.userId.toString() to "${it.fullName.ifBlank { it.username }} – ${it.roleLabel}" }

private val OPEN_LETTER = listOf("RECEIVED", "ASSIGNED")

fun inTray(me: zw.gov.chipingerdc.shared.model.Me, list: List<Correspondence>) =
    list.filter { it.status in OPEN_LETTER && (it.addressedTo == me.id || (it.addressedTo == null && it.assignedTo == me.id)) }

// ============================================================ incoming mail
@Composable
fun InTrayScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.CORRESPONDENCE, Correspondence.serializer()).collectAsState(initial = emptyList())
    val mine = inTray(ctx.me, list)
    AppScreen("Incoming mail", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("correspondence.manage")) zw.gov.chipingerdc.shared.ui.TopAction { PrimaryButton("+ Incoming letter", onClick = { ctx.go(Screen.NewCorrespondence) }) }
        ListScreen {
            if (mine.isEmpty()) item { Empty("No letters waiting for you.") }
            items(mine, key = { it.id }) { c ->
                RowCard(c.subject, "${c.reference} · from ${c.sender} · received ${prettyDate(c.dateReceived)}" +
                    (if (c.receivedByName.isNotBlank()) " by ${c.receivedByName}" else "") + (if (c.attachments.isNotEmpty()) " · scan attached" else "") +
                    (c.routingNote.takeIf { it.isNotBlank() }?.let { "\n$it" } ?: ""), null, c.statusLabel, c.status, c.localNote) {
                    ctx.go(Screen.CorrespondenceDetail(c.id))
                }
            }
            item {
                Text("All letters ›", color = CrdcColors.Blue, fontSize = 14.sp, modifier = Modifier.padding(12.dp).clickable { ctx.go(Screen.Correspondence) })
            }
        }
    }
}

@Composable
fun LetterDetailScreen(ctx: Ctx, id: String) {
    val cc by ctx.sdk.observeOne(Entities.CORRESPONDENCE, id, Correspondence.serializer()).collectAsState(initial = null)
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    val me = ctx.me
    AppScreen("Letter", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val c = cc ?: return@AppScreen Empty("Not found")
        val canRoute = c.localNote == null && c.status in OPEN_LETTER &&
            (c.addressedTo == me.id || c.assignedTo == me.id || me.can("correspondence.manage") || me.isCeo || (me.isHead && c.department == me.department))
        ScrollColumn {
            SectionCard(c.reference) {
                Text(c.subject, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Row { StatusChip(c.statusLabel, c.status) }
                c.localNote?.let { InfoBox(it) }
                KeyValue("From", "${c.sender} ${c.senderContact}".trim())
                KeyValue("Received", prettyDate(c.dateReceived) + (if (c.receivedByName.isNotBlank()) " by ${c.receivedByName}" else ""))
                c.addressedToName?.takeIf { it.isNotBlank() }?.let { KeyValue("Sent to", it) }
                KeyValue("Department", c.departmentLabel)
                c.assignedToName?.takeIf { it.isNotBlank() }?.let { KeyValue("Assigned to", it) }
                c.taskReference?.takeIf { it.isNotBlank() }?.let { KeyValue("Task", it) }
                KeyValue("Reply due", prettyDate(c.responseDue))
                if (c.fileReference.isNotBlank()) KeyValue("File reference", c.fileReference)
                if (c.routingNote.isNotBlank()) KeyValue("Notes", c.routingNote)
                if (c.responseSummary.isNotBlank()) KeyValue("Reply", c.responseSummary)
            }
            FilesCard(ctx.sdk, "correspondence", c.id, c.attachments, c.localNote == null && me.can("correspondence.manage"), "SCAN", "Scanned letter")
            if (canRoute) {
                PrimaryButton("Give task", onClick = { ctx.go(Screen.LetterAction(c.id, "task")) })
            }
        }
    }
}

@Composable
fun IncomingLetterScreen(ctx: Ctx) {
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    var sender by remember { mutableStateOf("") }
    var contact by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("") }
    var fileRef by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    val ceo = staff.firstOrNull { it.role == "CEO" }
    var to by remember { mutableStateOf("") }
    if (to.isBlank() && ceo != null) to = ceo.userId.toString()
    val files = remember { mutableStateListOf<PickedFile>() }
    AppScreen("Incoming letter", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            PendingFiles(files, "Scanned letter")
            Field("From", sender, { sender = it })
            Field("Sender's phone / address", contact, { contact = it })
            Field("Subject", subject, { subject = it })
            ChoicePicker("Send to", staffChoices(staff, ctx.me.id), to) { to = it }
            Field("Note to them", note, { note = it }, singleLine = false, minLines = 2)
            Field("File reference", fileRef, { fileRef = it })
            PrimaryButton("Send", enabled = sender.isNotBlank() && subject.isNotBlank() && to.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val target = staff.firstOrNull { it.userId.toString() == to }
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("sender", sender); put("subject", subject)
                    put("department", target?.department ?: "EXEC"); put("addressed_to_name", target?.fullName ?: "")
                    put("status", "RECEIVED"); put("status_label", "Waiting to send"); put("date_received", ctx.sdk.nowIso().take(10))
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved – sent when you are online")
                }
                ctx.sdk.enqueue("correspondence.create", "Letter from $sender", Entities.CORRESPONDENCE, id, optimistic) {
                    put("id", id); put("sender", sender); put("sender_contact", contact); put("subject", subject)
                    to.toLongOrNull()?.let { put("addressed_to", it) }; put("note", note); put("file_reference", fileRef)
                }
                val toSend = files.toList()
                if (toSend.isNotEmpty()) ctx.sdk.scope.launch {
                    runCatching { ctx.sdk.sync.sync(); toSend.forEach { uploadAttachment(ctx.sdk, "correspondence", id, "SCAN", it) }; ctx.sdk.sync.sync() }
                }
                ctx.back()
            })
        }
    }
}

// =========================================================== phone messages
@Composable
fun PhoneMessagesScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.PHONE_MESSAGES, PhoneMessage.serializer()).collectAsState(initial = emptyList())
    var show by remember { mutableStateOf("NEW") }
    val shown = list.filter { show == "ALL" || it.status == show }.sortedByDescending { it.createdAt }
    AppScreen("Phone messages", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("calls.log")) zw.gov.chipingerdc.shared.ui.TopAction { PrimaryButton("+ Take a message", onClick = { ctx.go(Screen.NewPhoneMessage) }) }
        Tabs(listOf("NEW" to "Open", "ALL" to "All"), show) { show = it }
        ListScreen {
            if (shown.isEmpty()) item { Empty("No messages.") }
            items(shown, key = { it.id }) { m ->
                SectionCard(m.callerName + (if (m.callerPhone.isNotBlank()) " – ${m.callerPhone}" else "")) {
                    Text(m.message, fontSize = 14.sp)
                    if (m.callBack) Text("Please call back", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text("For ${m.forUserName?.takeIf { it.isNotBlank() } ?: m.forDepartmentLabel} · taken by ${m.takenByName ?: ""} · ${prettyDate(m.createdAt)}",
                        fontSize = 12.sp, color = CrdcColors.Muted)
                    Row { StatusChip(m.statusLabel.ifBlank { "New" }, m.status) }
                    if (m.doneNote.isNotBlank()) KeyValue("Note", m.doneNote)
                    m.localNote?.let { InfoBox(it) }
                    if (m.status == "NEW" && m.localNote == null && (m.forUser == ctx.me.id || !ctx.me.can("calls.log")))
                        SecondaryButton("Done – called back", {
                            ctx.sdk.markPending(Entities.PHONE_MESSAGES, m.id, "Done – queued")
                            ctx.sdk.enqueue("phone_message.done", "Phone message ${m.callerName}", Entities.PHONE_MESSAGES, m.id) { put("id", m.id); put("note", "Called back") }
                        })
                }
            }
        }
    }
}

@Composable
fun NewPhoneMessageScreen(ctx: Ctx) {
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    var caller by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var forUser by remember { mutableStateOf("") }
    var forDept by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var callBack by remember { mutableStateOf(true) }
    AppScreen("Take a message", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Who called", caller, { caller = it })
            Field("Their phone number", phone, { phone = it })
            ChoicePicker("Message for", listOf("" to "—") + staffChoices(staff, ctx.me.id), forUser) { forUser = it }
            if (forUser.isBlank()) ChoicePicker("Or for the department", listOf("" to "—") + Choices.departments, forDept) { forDept = it }
            Field("Message", message, { message = it }, singleLine = false, minLines = 3)
            Row(Modifier.fillMaxWidth().clickable { callBack = !callBack }.padding(vertical = 4.dp)) {
                Text("Please call back", Modifier.weight(1f), fontSize = 15.sp)
                androidx.compose.material3.Switch(checked = callBack, onCheckedChange = { callBack = it })
            }
            PrimaryButton("Pass on", enabled = caller.isNotBlank() && message.isNotBlank() && (forUser.isNotBlank() || forDept.isNotBlank()), onClick = {
                val id = ctx.sdk.newId()
                val target = staff.firstOrNull { it.userId.toString() == forUser }
                val optimistic = buildJsonObject {
                    put("id", id); put("caller_name", caller); put("caller_phone", phone); put("message", message); put("call_back", callBack)
                    put("for_user_name", target?.fullName ?: ""); put("for_department_label", Choices.departments.firstOrNull { it.first == forDept }?.second ?: "")
                    put("taken_by_name", ctx.me.fullName); put("status", "NEW"); put("status_label", "Waiting to send"); put("created_at", ctx.sdk.nowIso())
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved – passed on when you are online")
                }
                ctx.sdk.enqueue("phone_message.create", "Phone message from $caller", Entities.PHONE_MESSAGES, id, optimistic) {
                    put("id", id); put("caller_name", caller); put("caller_phone", phone); put("message", message); put("call_back", callBack)
                    forUser.toLongOrNull()?.let { put("for_user", it) }; put("for_department", forDept)
                }
                ctx.back()
            })
        }
    }
}


/** Give the letter to a person as a task; the letter is filed with the task. */
@Composable
fun LetterActionScreen(ctx: Ctx, id: String, @Suppress("UNUSED_PARAMETER") action: String) {
    val cc by ctx.sdk.observeOne(Entities.CORRESPONDENCE, id, Correspondence.serializer()).collectAsState(initial = null)
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    var toUser by remember { mutableStateOf("") }
    var what by remember { mutableStateOf("") }
    var due by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    AppScreen("Give task", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val c = cc ?: return@AppScreen Empty("Not found")
        if (what.isBlank()) what = c.subject
        ScrollColumn {
            SectionCard(c.reference) {
                Text(c.subject, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text("From ${c.sender}", fontSize = 13.sp, color = CrdcColors.Muted)
            }
            ChoicePicker("Who will do it", listOf("" to "—") + staffChoices(staff, ctx.me.id), toUser) { toUser = it }
            Field("What must be done", what, { what = it })
            Field("Due date (YYYY-MM-DD)", due, { due = it })
            Field("Instructions", note, { note = it }, singleLine = false, minLines = 3)
            PrimaryButton("Give task", enabled = toUser.isNotBlank(), onClick = {
                ctx.sdk.markPending(Entities.CORRESPONDENCE, c.id, "Task queued")
                ctx.sdk.enqueue("letter.route", "Letter ${c.reference}: task", Entities.CORRESPONDENCE, c.id) {
                    put("id", c.id); put("action", "task"); put("to_user", toUser); put("title", what); put("note", note)
                    if (due.isNotBlank()) put("due_date", due)
                }
                ctx.back()
            })
        }
    }
}
