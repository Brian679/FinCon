package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
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
import zw.gov.chipingerdc.shared.model.AppNotification
import zw.gov.chipingerdc.shared.model.AuditFinding
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.LeaveRequest
import zw.gov.chipingerdc.shared.model.Project
import zw.gov.chipingerdc.shared.model.ServiceStandard
import zw.gov.chipingerdc.shared.model.StandApplication
import zw.gov.chipingerdc.shared.platformName
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
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

@Composable
fun ProjectsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.PROJECTS, Project.serializer()).collectAsState(initial = emptyList())
    AppScreen("Projects", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No projects.") }
            items(list, key = { it.id }) { p ->
                RowCard(p.name, "${p.code} · ${p.categoryLabel} · Ward ${p.ward ?: "-"}\nBudget $${money(p.budget)} · ${p.funder.ifBlank { "Council" }}",
                    "${p.progress}%", p.statusLabel, p.status) { ctx.go(Screen.ProjectDetail(p.id)) }
            }
        }
    }
}

@Composable
fun StandsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.STANDS, q, StandApplication.serializer()).collectAsState(initial = emptyList())
    AppScreen("Stand applications", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("stands.manage")) PrimaryButton("+ Capture application", onClick = { ctx.go(Screen.NewStand) })
        Field("Search", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No applications.") }
            items(list, key = { it.id }) { s ->
                RowCard(s.applicantName, "${s.reference} · ${s.standTypeLabel} · ${s.preferredLocation}" +
                    if (s.allocatedStand.isNotBlank()) "\nAllocated: ${s.allocatedStand}" else "", null, s.statusLabel, s.status) { ctx.go(Screen.StandDetail(s.id)) }
            }
        }
    }
}

@Composable
fun StandFormScreen(ctx: Ctx) {
    var name by remember { mutableStateOf("") }
    var nid by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("RES") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    AppScreen("Stand application", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Applicant name", name, { name = it })
            Field("National ID", nid, { nid = it })
            Field("Phone", phone, { phone = it })
            ChoicePicker("Stand type", Choices.standTypes, type) { type = it }
            Field("Preferred location", location, { location = it })
            Field("Ward", ward, { ward = it }, number = true)
            PrimaryButton("Save", enabled = name.isNotBlank() && nid.isNotBlank() && location.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("applicant_name", name); put("national_id", nid); put("stand_type", type)
                    put("preferred_location", location); put("status", "RECEIVED"); put("status_label", "Pending sync"); put("updated_at", now)
                }
                ctx.sdk.enqueue("stand.create", "Stand application: $name", Entities.STANDS, id, optimistic) {
                    put("id", id); put("applicant_name", name); put("national_id", nid); put("phone", phone); put("stand_type", type)
                    put("preferred_location", location); ward.toIntOrNull()?.let { put("ward", it) }
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun FindingsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.AUDIT_FINDINGS, AuditFinding.serializer()).collectAsState(initial = emptyList())
    AppScreen("Internal audit findings", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No findings.") }
            items(list, key = { it.id }) { f ->
                RowCard(f.title, "${f.reference} · ${f.auditTypeLabel} · ${f.departmentLabel}\nRisk: ${f.riskRatingLabel}", null, f.statusLabel,
                    if (f.riskRating in listOf("HIGH", "CRITICAL")) "URGENT" else f.status) { ctx.go(Screen.FindingDetail(f.id)) }
            }
        }
    }
}

@Composable
fun LeaveScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.LEAVE, LeaveRequest.serializer()).collectAsState(initial = emptyList())
    AppScreen("Leave", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Apply for leave", onClick = { ctx.go(Screen.NewLeave) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No leave applications.") }
            items(list, key = { it.id }) { l ->
                RowCard(l.employeeName.ifBlank { ctx.me.fullName }, "${l.leaveTypeLabel} · ${l.startDate} – ${l.endDate}\n${l.decisionComment}", null,
                    l.statusLabel.ifBlank { l.status }, l.status, l.localNote)
            }
        }
    }
}

@Composable
fun LeaveFormScreen(ctx: Ctx) {
    var type by remember { mutableStateOf("ANNUAL") }
    var start by remember { mutableStateOf("") }
    var end by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    val valid = Regex("""\d{4}-\d{2}-\d{2}""")
    AppScreen("Apply for leave", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Leave type", Choices.leaveTypes, type) { type = it }
            Field("Start date (YYYY-MM-DD)", start, { start = it })
            Field("End date (YYYY-MM-DD)", end, { end = it })
            Field("Reason", reason, { reason = it }, singleLine = false, minLines = 2)
            PrimaryButton("Submit", enabled = valid.matches(start) && valid.matches(end) && end >= start, onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val optimistic = buildJsonObject {
                    put("id", id); put("employee", ctx.me.id); put("employee_name", ctx.me.fullName); put("leave_type", type); put("start_date", start)
                    put("end_date", end); put("status", "PENDING"); put("status_label", "Pending sync"); put("updated_at", now)
                    put("local_note", "Saved on phone – will sync")
                }
                ctx.sdk.enqueue("leave.apply", "Leave $start – $end", Entities.LEAVE, id, optimistic) {
                    put("id", id); put("leave_type", type); put("start_date", start); put("end_date", end); put("reason", reason)
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun NotificationsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.NOTIFICATIONS, AppNotification.serializer()).collectAsState(initial = emptyList())
    AppScreen("Notifications", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No notifications.") }
            items(list.sortedByDescending { it.createdAt }, key = { it.id }) { n ->
                RowCard(n.title, n.body + "\n" + prettyDate(n.createdAt), null, if (n.isRead) null else "New", "PENDING") {
                    if (!n.isRead) {
                        ctx.sdk.markPending(Entities.NOTIFICATIONS, n.id, "", mapOf())
                        ctx.sdk.enqueue("notification.read", "Read notification", Entities.NOTIFICATIONS, n.id) { put("notification", n.id) }
                    }
                }
            }
        }
    }
}

@Composable
fun SyncCentreScreen(ctx: Ctx) {
    val ops by ctx.sdk.outbox.collectAsState(initial = emptyList())
    AppScreen("Sync centre", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item {
                SectionCard("This phone") {
                    KeyValue("Server", ctx.sdk.session.baseUrl)
                    KeyValue("Last sync", prettyDate(ctx.sync.lastSync))
                    KeyValue("Connection", when (ctx.sync.online) { true -> "Online"; false -> "Offline"; null -> "Unknown" })
                    KeyValue("Waiting to upload", ctx.pending.toString())
                    KeyValue("Device", "$platformName · ${ctx.sdk.session.deviceId.take(8)}")
                    if (ctx.sync.lastError != null) InfoBox(ctx.sync.lastError!!, CrdcColors.Warning)
                    PrimaryButton("Sync now", busy = ctx.sync.running, onClick = { ctx.syncNow() })
                }
            }
            if (ops.isEmpty()) item { Empty("Everything has been uploaded.") }
            items(ops, key = { it.op_id }) { op ->
                SectionCard(op.summary.ifBlank { op.type }) {
                    Text("${op.type} · captured ${prettyDate(op.created_at)} · attempts ${op.attempts}", fontSize = 12.sp, color = CrdcColors.Muted)
                    if (op.status == "REJECTED") {
                        InfoBox("Rejected by the server: ${op.error}", CrdcColors.Danger)
                        SecondaryButton("Dismiss", { ctx.sdk.dismissRejected(op.op_id) })
                    } else Text("Waiting to upload", color = CrdcColors.Blue, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun CharterScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.SERVICE_STANDARDS, ServiceStandard.serializer()).collectAsState(initial = emptyList())
    AppScreen("Client Charter 2026-2030", onBack = ctx::back) {
        ListScreen {
            item {
                SectionCard("Vision") { Text("A Provider of Responsive Quality Municipal Services by 2030.") }
            }
            item {
                SectionCard("Core values – PITTA") {
                    Text("Proactive · Integrity · Teamwork · Transparency · Accountability")
                }
            }
            item {
                SectionCard("Service standards") {
                    list.forEach { KeyValue(it.service, it.standardText) }
                }
            }
            item {
                SectionCard("Our service pledge") {
                    Text("“We are committed to responsive, transparent, accountable and quality municipal service delivery for sustainable development and improved quality of life for all residents of Chipinge District.”")
                }
            }
        }
    }
}
