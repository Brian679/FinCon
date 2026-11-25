package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import zw.gov.chipingerdc.shared.model.AppNotification
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.ServiceRequest
import zw.gov.chipingerdc.shared.model.Task
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.isPast
import zw.gov.chipingerdc.shared.ui.money

private data class Tile(val label: String, val screen: Screen, val badge: Int = 0)

@Composable
fun HomeScreen(ctx: Ctx) {
    val me = ctx.me
    val sdk = ctx.sdk
    val receipts by sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    val tasks by sdk.observe(Entities.TASKS, Task.serializer()).collectAsState(initial = emptyList())
    val complaints by sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    val requests by sdk.observe(Entities.SERVICE_REQUESTS, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    val notes by sdk.observe(Entities.NOTIFICATIONS, AppNotification.serializer()).collectAsState(initial = emptyList())
    val approvals = rememberApprovals(ctx)

    val today = Clock.System.now().toLocalDateTime(TimeZone.of("Africa/Harare")).date.toString()
    val myToday = receipts.filter { it.createdAt.startsWith(today) && it.status != "VOIDED" && (it.receivedBy == me.id || it.localNote != null) }
    val myTasks = tasks.filter { it.assignedToName == me.fullName && it.status in listOf("OPEN", "IN_PROGRESS") }
    val openComplaints = complaints.filter { it.status !in listOf("RESOLVED", "CLOSED") }
    val unacked = openComplaints.count { it.acknowledgedAt == null }
    val openRequests = requests.filter { it.status !in listOf("RESOLVED", "CLOSED", "REJECTED") }
    val unread = notes.count { !it.isRead }

    val tiles = buildList {
        if (me.can("receipt.create")) add(Tile("Issue receipt", Screen.NewReceipt))
        if (me.can("finance.view")) add(Tile("Receipts", Screen.Receipts))
        if (me.can("accounts.manage", "finance.view_all", "receipt.create")) add(Tile("Client accounts", Screen.Accounts))
        add(Tile("Approvals", Screen.Approvals, approvals.size))
        if (me.can("licence.view")) add(Tile("Licences", Screen.Licences))
        if (me.can("budget.view")) add(Tile("Budget vs actual", Screen.Budget))
        add(Tile("Tasks", Screen.Tasks, myTasks.size))
        add(Tile("Complaints", Screen.Complaints, unacked))
        add(Tile("Service requests", Screen.Requests, openRequests.count { isPast(it.dueAt) }))
        if (me.can("projects.view")) add(Tile("Projects", Screen.Projects))
        if (me.can("stands.view")) add(Tile("Stand applications", Screen.Stands))
        if (me.can("audit.findings_view", "audit.respond")) add(Tile("Audit findings", Screen.Findings))
        add(Tile("Leave", Screen.Leave))
        add(Tile("Notifications", Screen.Notifications, unread))
        add(Tile("Sync centre", Screen.SyncCentre, ctx.pending.toInt()))
        add(Tile("Client Charter", Screen.Charter))
    }

    AppScreen("Chipinge RDC", sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow, actions = {
        TextButton(onClick = { ctx.sdk.logout() }) { Text("Log out", color = Color.White) }
    }) {
        ScrollColumn {
            Text("Welcome, ${me.fullName.ifBlank { me.username }}", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text("${me.roleLabel} · ${me.departmentLabel}", color = CrdcColors.Muted)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (me.can("receipt.create")) {
                    val usd = myToday.filter { it.currency == "USD" }.sumOf { it.amount.toDoubleOrNull() ?: 0.0 }
                    Kpi("My collections today", "$${money(usd.toString())}", "${myToday.size} receipt(s)", modifier = Modifier.weight(1f)) { ctx.go(Screen.Receipts) }
                }
                Kpi("Waiting for me", approvals.size.toString(), "approvals", CrdcColors.Warning, Modifier.weight(1f)) { ctx.go(Screen.Approvals) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Open complaints", openComplaints.size.toString(), "$unacked not acknowledged (48h)", if (unacked > 0) CrdcColors.Danger else CrdcColors.Green, Modifier.weight(1f)) { ctx.go(Screen.Complaints) }
                Kpi("Service requests", openRequests.size.toString(), "${openRequests.count { isPast(it.dueAt) }} overdue", CrdcColors.Blue, Modifier.weight(1f)) { ctx.go(Screen.Requests) }
            }
            SectionCard("What would you like to do?") {
                tiles.chunked(2).forEach { pair ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        pair.forEach { t ->
                            Kpi(t.label, if (t.badge > 0) t.badge.toString() else "›", null,
                                if (t.badge > 0) CrdcColors.Warning else CrdcColors.Green, Modifier.weight(1f)) { ctx.go(t.screen) }
                        }
                        if (pair.size == 1) androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
                    }
                }
            }
        }
    }
}
