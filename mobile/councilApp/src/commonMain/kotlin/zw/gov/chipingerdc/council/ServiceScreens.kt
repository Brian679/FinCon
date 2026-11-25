package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.ServiceRequest
import zw.gov.chipingerdc.shared.model.Task
import zw.gov.chipingerdc.shared.model.TaskComment
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.Progress
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.isPast
import zw.gov.chipingerdc.shared.ui.prettyDate

// --------------------------------------------------------------------- tasks
@Composable
fun TasksScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.TASKS, Task.serializer()).collectAsState(initial = emptyList())
    var showClosed by remember { mutableStateOf(false) }
    val shown = list.filter { showClosed || it.status in listOf("OPEN", "IN_PROGRESS", "DONE") }
    AppScreen("Tasks & requests", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        SecondaryButton(if (showClosed) "Hide closed" else "Show closed", { showClosed = !showClosed }, Modifier.padding(12.dp))
        ListScreen {
            if (shown.isEmpty()) item { Empty("No tasks.") }
            items(shown, key = { it.id }) { t ->
                val overdue = t.dueDate != null && t.status in listOf("OPEN", "IN_PROGRESS") && isPast(t.dueDate + "T23:59:59Z")
                RowCard(t.title, "${t.reference} · ${t.kindLabel} · from ${t.assignedByName}\nDue ${prettyDate(t.dueDate)}${if (overdue) " – OVERDUE" else ""}",
                    "${t.progress}%", t.statusLabel, if (overdue) "URGENT" else t.status, t.localNote) { ctx.go(Screen.TaskDetail(t.id)) }
            }
        }
    }
}

@Composable
fun TaskDetailScreen(ctx: Ctx, id: String) {
    val t by ctx.sdk.observeOne(Entities.TASKS, id, Task.serializer()).collectAsState(initial = null)
    val comments by ctx.sdk.observe(Entities.TASK_COMMENTS, TaskComment.serializer()).collectAsState(initial = emptyList())
    var progress by remember(t?.progress) { mutableStateOf((t?.progress ?: 0).toFloat()) }
    var status by remember { mutableStateOf("") }
    var comment by remember { mutableStateOf("") }
    AppScreen("Task", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val task = t ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(task.title) {
                KeyValue("Reference", task.reference)
                KeyValue("Type", task.kindLabel)
                KeyValue("From", task.assignedByName)
                KeyValue("To", task.assignedToName ?: "Head of ${task.departmentLabel}")
                KeyValue("Priority", task.priorityLabel)
                KeyValue("Due", prettyDate(task.dueDate))
                KeyValue("Status", task.statusLabel)
                Progress(task.progress)
                Text(task.description)
                if (task.localNote != null) InfoBox(task.localNote!!)
            }
            SectionCard("Conversation") {
                val mine = comments.filter { it.task == task.id }.sortedBy { it.createdAt }
                if (mine.isEmpty()) Text("No comments yet.", color = CrdcColors.Muted)
                mine.forEach { c -> KeyValue(c.authorName, c.body + "\n" + prettyDate(c.createdAt)) }
            }
            SectionCard("Report back / update") {
                Text("Progress: ${progress.toInt()}%", fontSize = 13.sp)
                Slider(value = progress, onValueChange = { progress = it }, valueRange = 0f..100f, steps = 9)
                ChoicePicker("Status", listOf("" to "(no change)") + Choices.taskStatuses, status) { status = it }
                Field("Comment", comment, { comment = it }, singleLine = false, minLines = 3)
                PrimaryButton("Save update", onClick = {
                    ctx.sdk.markPending(Entities.TASKS, task.id, "Update queued")
                    ctx.sdk.enqueue("task.update", "Task ${task.reference} update", Entities.TASKS, task.id) {
                        put("task", task.id); put("progress", progress.toInt()); if (status.isNotBlank()) put("status", status); put("comment", comment)
                    }
                    comment = ""
                })
            }
        }
    }
}

// ---------------------------------------------------------------- complaints
@Composable
fun ComplaintsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.COMPLAINTS, q, Complaint.serializer()).collectAsState(initial = emptyList())
    AppScreen("Complaints & feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Record complaint / feedback", onClick = { ctx.go(Screen.NewComplaint) })
        Field("Search", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No complaints.") }
            items(list, key = { it.id }) { c ->
                val breached = c.acknowledgedAt == null && isPast(c.acknowledgeDue)
                RowCard(c.subject, "${c.reference} · ${c.kindLabel} · ${c.departmentLabel}\n${c.name} · ${prettyDate(c.createdAt)}" +
                    if (breached) "\n48-hour acknowledgement standard breached" else "",
                    null, c.statusLabel, if (breached) "URGENT" else c.status, c.localNote) { ctx.go(Screen.ComplaintDetail(c.id)) }
            }
        }
    }
}

@Composable
fun ComplaintDetailScreen(ctx: Ctx, id: String) {
    val c by ctx.sdk.observeOne(Entities.COMPLAINTS, id, Complaint.serializer()).collectAsState(initial = null)
    var note by remember { mutableStateOf("") }
    AppScreen("Complaint", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val cp = c ?: return@AppScreen Empty("Not found")
        fun act(action: String) {
            ctx.sdk.markPending(Entities.COMPLAINTS, cp.id, "$action queued")
            ctx.sdk.enqueue("complaint.action", "Complaint ${cp.reference}: $action", Entities.COMPLAINTS, cp.id) {
                put("complaint", cp.id); put("action", action); put("note", note)
            }
            note = ""
        }
        ScrollColumn {
            SectionCard(cp.subject) {
                KeyValue("Reference", cp.reference)
                KeyValue("Type", "${cp.kindLabel} via ${cp.channelLabel}")
                KeyValue("From", "${cp.name} ${cp.phone}")
                KeyValue("Department", cp.departmentLabel)
                KeyValue("Received", prettyDate(cp.createdAt))
                KeyValue("Acknowledge by", prettyDate(cp.acknowledgeDue))
                KeyValue("Acknowledged", prettyDate(cp.acknowledgedAt))
                KeyValue("Feedback due", prettyDate(cp.responseDue))
                KeyValue("Status", cp.statusLabel)
                KeyValue("Resolution", cp.resolution)
                Text(cp.details)
                if (cp.localNote != null) InfoBox(cp.localNote!!)
            }
            if (cp.status != "CLOSED" && cp.localNote == null) SectionCard("Action") {
                Field("Note / feedback to client", note, { note = it }, singleLine = false, minLines = 2)
                if (cp.acknowledgedAt == null) PrimaryButton("Acknowledge", color = CrdcColors.Warning, onClick = { act("acknowledge") })
                if (cp.status != "RESOLVED") PrimaryButton("Mark resolved", enabled = note.isNotBlank(), onClick = { act("resolve") })
                if (cp.status == "RESOLVED") SecondaryButton("Close", { act("close") })
            }
        }
    }
}

@Composable
fun ComplaintFormScreen(ctx: Ctx) {
    var kind by remember { mutableStateOf("COMPLAINT") }
    var channel by remember { mutableStateOf("OFFICE") }
    var dept by remember { mutableStateOf(ctx.me.department.ifBlank { "ADMIN" }) }
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("") }
    var details by remember { mutableStateOf("") }
    AppScreen("Record complaint / feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Type", Choices.complaintKinds, kind) { kind = it }
            ChoicePicker("Received via", Choices.complaintChannels, channel) { channel = it }
            ChoicePicker("Department responsible", Choices.departments, dept) { dept = it }
            Field("Client name", name, { name = it })
            Field("Phone", phone, { phone = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("Subject", subject, { subject = it })
            Field("Details", details, { details = it }, singleLine = false, minLines = 4)
            PrimaryButton("Save", enabled = subject.isNotBlank() && details.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("kind", kind); put("subject", subject); put("details", details)
                    put("name", name); put("department", dept); put("status", "RECEIVED"); put("status_label", "Pending sync")
                    put("created_at", now); put("updated_at", now); put("local_note", "Saved on phone – will sync")
                }
                ctx.sdk.enqueue("complaint.create", "Complaint: $subject", Entities.COMPLAINTS, id, optimistic) {
                    put("id", id); put("kind", kind); put("channel", channel); put("department", dept); put("name", name); put("phone", phone)
                    ward.toIntOrNull()?.let { put("ward", it) }; put("subject", subject); put("details", details); put("captured_at", now)
                }
                ctx.back()
            })
            Text("The 48-hour acknowledgement clock starts from when you capture it, even if the phone is offline.", fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

// ---------------------------------------------------------- service requests
@Composable
fun RequestsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.SERVICE_REQUESTS, q, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    AppScreen("Service requests & faults", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Log fault / service request", onClick = { ctx.go(Screen.NewRequest) })
        Field("Search", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No service requests.") }
            items(list, key = { it.id }) { s ->
                val overdue = isPast(s.dueAt) && s.status !in listOf("RESOLVED", "CLOSED", "REJECTED")
                RowCard(s.categoryLabel, "${s.reference} · ${s.location} · Ward ${s.ward ?: "-"}\nDue ${prettyDate(s.dueAt)}${if (overdue) " – OVERDUE" else ""}",
                    s.priorityLabel, s.statusLabel, if (overdue) "URGENT" else s.status, s.localNote) { ctx.go(Screen.RequestDetail(s.id)) }
            }
        }
    }
}

@Composable
fun RequestDetailScreen(ctx: Ctx, id: String) {
    val s by ctx.sdk.observeOne(Entities.SERVICE_REQUESTS, id, ServiceRequest.serializer()).collectAsState(initial = null)
    var note by remember { mutableStateOf("") }
    AppScreen("Service request", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val sr = s ?: return@AppScreen Empty("Not found")
        fun act(action: String) {
            ctx.sdk.markPending(Entities.SERVICE_REQUESTS, sr.id, "$action queued")
            ctx.sdk.enqueue("service_request.action", "${sr.reference}: $action", Entities.SERVICE_REQUESTS, sr.id) {
                put("service_request", sr.id); put("action", action); put("note", note)
            }
            note = ""
        }
        ScrollColumn {
            SectionCard(sr.categoryLabel) {
                KeyValue("Reference", sr.reference)
                KeyValue("Location", "${sr.location} · Ward ${sr.ward ?: "-"}")
                KeyValue("Reported by", "${sr.reporterName} ${sr.reporterPhone}")
                KeyValue("Reported", prettyDate(sr.createdAt))
                KeyValue("Charter deadline", prettyDate(sr.dueAt))
                KeyValue("Priority", sr.priorityLabel)
                KeyValue("Status", sr.statusLabel)
                KeyValue("Resolution", sr.resolution)
                Text(sr.description)
                if (sr.localNote != null) InfoBox(sr.localNote!!)
            }
            if (sr.status !in listOf("CLOSED", "REJECTED") && sr.localNote == null) SectionCard("Field update") {
                Field("Work done / note", note, { note = it }, singleLine = false, minLines = 2)
                if (sr.status in listOf("REPORTED", "ASSIGNED")) PrimaryButton("Start work", color = CrdcColors.Warning, onClick = { act("start") })
                if (sr.status != "RESOLVED") PrimaryButton("Mark resolved", enabled = note.isNotBlank(), onClick = { act("resolve") })
                if (sr.status == "RESOLVED") SecondaryButton("Close", { act("close") })
            }
        }
    }
}

@Composable
fun RequestFormScreen(ctx: Ctx) {
    var category by remember { mutableStateOf("WATER_FAULT") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    AppScreen("Log service request", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Category", Choices.serviceCategories, category) { category = it }
            Field("Location / landmark", location, { location = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("Description", description, { description = it }, singleLine = false, minLines = 3)
            Field("Reported by (name)", name, { name = it })
            Field("Reporter phone", phone, { phone = it })
            PrimaryButton("Save", enabled = location.isNotBlank() && description.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val label = Choices.serviceCategories.first { it.first == category }.second
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("category", category); put("category_label", label); put("location", location)
                    put("description", description); put("status", "REPORTED"); put("status_label", "Pending sync"); put("created_at", now)
                    put("updated_at", now); put("local_note", "Saved on phone – will sync")
                }
                ctx.sdk.enqueue("service_request.create", "Fault: $label at $location", Entities.SERVICE_REQUESTS, id, optimistic) {
                    put("id", id); put("category", category); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("description", description); put("reporter_name", name); put("reporter_phone", phone); put("captured_at", now)
                }
                ctx.back()
            })
        }
    }
}
