package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import zw.gov.chipingerdc.shared.model.Asset
import zw.gov.chipingerdc.shared.model.BudgetLine
import zw.gov.chipingerdc.shared.model.BuildingPlan
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.CommunityActivity
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.IctTicket
import zw.gov.chipingerdc.shared.model.Incident
import zw.gov.chipingerdc.shared.model.LeaveRequest
import zw.gov.chipingerdc.shared.model.Project
import zw.gov.chipingerdc.shared.model.Requisition
import zw.gov.chipingerdc.shared.model.Resolution
import zw.gov.chipingerdc.shared.model.Risk
import zw.gov.chipingerdc.shared.model.ServiceRequest
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.model.StandApplication
import zw.gov.chipingerdc.shared.model.Task
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.Progress
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.isPast
import zw.gov.chipingerdc.shared.ui.money

private val OPEN_TASK = listOf("OPEN", "IN_PROGRESS")

/** Head of Department view of everything happening in the department (CEO / auditors can pick any department). */
@Composable
fun DepartmentScreen(ctx: Ctx, deptArg: String?) {
    val sdk = ctx.sdk
    val me = ctx.me
    val canSwitch = me.isCeo || me.can("audit.view_all", "dept.overview_all")
    var dept by remember { mutableStateOf(deptArg ?: me.department) }
    val staff by sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    val tasks by sdk.observe(Entities.TASKS, Task.serializer()).collectAsState(initial = emptyList())
    val reqs by sdk.observe(Entities.REQUISITIONS, Requisition.serializer()).collectAsState(initial = emptyList())
    val leave by sdk.observe(Entities.LEAVE, LeaveRequest.serializer()).collectAsState(initial = emptyList())
    val budget by sdk.observe(Entities.BUDGET_LINES, BudgetLine.serializer()).collectAsState(initial = emptyList())
    val complaints by sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    val requests by sdk.observe(Entities.SERVICE_REQUESTS, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    val activities by sdk.observe(Entities.ACTIVITIES, CommunityActivity.serializer()).collectAsState(initial = emptyList())
    val incidents by sdk.observe(Entities.INCIDENTS, Incident.serializer()).collectAsState(initial = emptyList())
    val stands by sdk.observe(Entities.STANDS, StandApplication.serializer()).collectAsState(initial = emptyList())
    val projects by sdk.observe(Entities.PROJECTS, Project.serializer()).collectAsState(initial = emptyList())
    val plans by sdk.observe(Entities.BUILDING_PLANS, BuildingPlan.serializer()).collectAsState(initial = emptyList())
    val assets by sdk.observe(Entities.ASSETS, Asset.serializer()).collectAsState(initial = emptyList())
    val tickets by sdk.observe(Entities.ICT_TICKETS, IctTicket.serializer()).collectAsState(initial = emptyList())
    val resolutions by sdk.observe(Entities.RESOLUTIONS, Resolution.serializer()).collectAsState(initial = emptyList())
    val risks by sdk.observe(Entities.RISKS, Risk.serializer()).collectAsState(initial = emptyList())

    val deptStaff = staff.filter { it.department == dept && it.isActive }
    val deptTasks = tasks.filter { it.department == dept && it.status in OPEN_TASK }
    val waitingReqs = reqs.filter { it.department == dept && it.status == "SUBMITTED" }
    val waitingLeave = leave.filter { it.employeeDepartment == dept && it.status == "PENDING" }
    val toVerify = activities.filter { it.department == dept && it.status == "DONE" }
    val openComplaints = complaints.filter { it.department == dept && it.status !in listOf("RESOLVED", "CLOSED") }
    val openRequests = requests.filter { it.department == dept && it.status !in listOf("RESOLVED", "CLOSED", "REJECTED") }
    val label = Choices.departments.firstOrNull { it.first == dept }?.second ?: dept

    AppScreen("$label – overview", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (canSwitch) ChoicePicker("Department", Choices.departments, dept) { dept = it }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Waiting for HOD", (waitingReqs.size + waitingLeave.size + toVerify.size).toString(), "requisitions · leave · reports",
                    CrdcColors.Warning, Modifier.weight(1f))
                Kpi("Open tasks", deptTasks.size.toString(), "${deptTasks.count { it.dueDate != null && isPast(it.dueDate + "T23:59:59Z") }} overdue",
                    CrdcColors.Blue, Modifier.weight(1f)) { ctx.go(Screen.Tasks) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Complaints", openComplaints.size.toString(), "${openComplaints.count { it.acknowledgedAt == null }} not acknowledged",
                    if (openComplaints.any { it.acknowledgedAt == null }) CrdcColors.Danger else CrdcColors.Green, Modifier.weight(1f)) { ctx.go(Screen.Complaints) }
                Kpi("Service requests", openRequests.size.toString(), "${openRequests.count { isPast(it.dueAt) }} overdue",
                    CrdcColors.Blue, Modifier.weight(1f)) { ctx.go(Screen.Requests) }
            }
            // Department-specific registers
            val special: List<Triple<String, Int, Screen>> = when (dept) {
                "SOCIAL" -> listOf(
                    Triple("Open incidents", incidents.count { it.status != "CLOSED" }, Screen.Incidents),
                    Triple("Stand applications waiting", stands.count { it.status == "RECEIVED" }, Screen.Stands),
                    Triple("Boreholes / ablutions broken", assets.count { it.category in listOf("BOREHOLE", "ABLUTION", "WATER") && it.condition == "BROKEN" }, Screen.Assets),
                    Triple("Programmes this month", activities.count { it.department == dept }, Screen.Activities),
                )
                "TECH" -> listOf(
                    Triple("Projects ongoing", projects.count { it.status == "ONGOING" }, Screen.Projects),
                    Triple("Plans awaiting decision", plans.count { it.status in listOf("SUBMITTED", "REVIEW", "RECOMMEND") }, Screen.Plans),
                    Triple("Plans past 30 working days", plans.count { it.status in listOf("SUBMITTED", "REVIEW", "RECOMMEND") && isPast(it.dueAt) }, Screen.Plans),
                    Triple("Lights / roads faulty", assets.count { it.category in listOf("LIGHT", "ROAD", "BRIDGE") && it.condition in listOf("POOR", "BROKEN") }, Screen.Assets),
                )
                "ADMIN" -> listOf(
                    Triple("ICT tickets open", tickets.count { it.status in listOf("OPEN", "IN_PROGRESS") }, Screen.Tickets),
                    Triple("Resolutions not implemented", resolutions.count { it.status !in listOf("DONE", "RESCINDED") }, Screen.Resolutions),
                )
                "AUDIT" -> listOf(
                    Triple("High / critical risks", risks.count { it.rating in listOf("HIGH", "CRITICAL") && it.status != "CLOSED" }, Screen.Risks),
                )
                "FINANCE" -> listOf(
                    Triple("Requisitions in approval", reqs.count { it.status in listOf("HOD_OK", "FIN_OK", "APPROVED") }, Screen.Requisitions),
                )
                else -> emptyList()
            }
            special.chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { (l, v, sc) -> Kpi(l, v.toString(), null, CrdcColors.Blue, Modifier.weight(1f)) { ctx.go(sc) } }
                    if (pair.size == 1) androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
                }
            }
            SectionCard("Waiting for the Head of Department") {
                if (waitingReqs.isEmpty() && waitingLeave.isEmpty() && toVerify.isEmpty()) Text("Nothing waiting.", color = CrdcColors.Muted)
                waitingReqs.forEach { r -> RowCard("Requisition ${r.number}", "${r.requestedByName} · ${r.purpose}", "$${money(r.total)}") { ctx.go(Screen.RequisitionDetail(r.id)) } }
                waitingLeave.forEach { l -> RowCard("Leave: ${l.employeeName}", "${l.leaveTypeLabel} ${l.startDate} – ${l.endDate}", null, "Approve", "PENDING") { ctx.go(Screen.Approvals) } }
                toVerify.forEach { a -> RowCard("Activity report: ${a.title}", "${a.officerName} · ${a.participants} participants") { ctx.go(Screen.ActivityDetail(a.id)) } }
            }
            SectionCard("Staff (${deptStaff.size})") {
                deptStaff.forEach { s ->
                    val mine = deptTasks.filter { it.assignedToName == s.fullName }
                    KeyValue(s.fullName, "${s.roleLabel} · ${mine.size} open task(s)")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(Modifier.weight(1f)) { PrimaryButton("Assign task", onClick = { ctx.go(Screen.NewTask) }) }
                    Row(Modifier.weight(1f)) { PrimaryButton("New requisition", color = CrdcColors.Blue, onClick = { ctx.go(Screen.NewRequisition) }) }
                }
            }
            SectionCard("Budget ${budget.firstOrNull()?.financialYear ?: ""}") {
                val lines = budget.filter { it.department == dept }
                if (lines.isEmpty()) Text("No budget votes synced for this department.", color = CrdcColors.Muted)
                lines.forEach { b ->
                    val total = (b.revisedAmount ?: b.approvedAmount).toDoubleOrNull() ?: 0.0
                    val used = (b.actual.toDoubleOrNull() ?: 0.0) + (b.committed.toDoubleOrNull() ?: 0.0)
                    val pct = if (total > 0) (used / total * 100).toInt() else 0
                    Text("${b.voteCode} ${b.description} – $pct% of $${money(total.toString())}", fontSize = 13.sp)
                    Progress(pct)
                }
            }
        }
    }
}

@Composable
fun NewTaskScreen(ctx: Ctx) {
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    val me = ctx.me
    val choices = staff.filter { it.isActive && it.userId != me.id && (me.can("tasks.assign_any") || it.department == me.department) }
    var kind by remember { mutableStateOf("TASK") }
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var assignee by remember { mutableStateOf<StaffMember?>(null) }
    var priority by remember { mutableStateOf("NORMAL") }
    var due by remember { mutableStateOf("") }
    AppScreen("Assign task / request / memo", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (!me.can("tasks.assign_any", "tasks.assign_department")) {
                InfoBox("Only heads of department and the CEO can assign tasks.", CrdcColors.Warning)
                return@ScrollColumn
            }
            ChoicePicker("Type", Choices.taskKinds, kind) { kind = it }
            Field("Title", title, { title = it })
            Field("Instructions", description, { description = it }, singleLine = false, minLines = 3)
            Picker("Assign to", choices, assignee, { "${it.fullName} – ${it.roleLabel}" }, { assignee = it })
            ChoicePicker("Priority", Choices.priorities, priority) { priority = it }
            Field("Due date (YYYY-MM-DD, optional)", due, { due = it })
            PrimaryButton("Send", enabled = title.isNotBlank() && assignee != null, onClick = {
                val a = assignee!!
                ctx.sdk.enqueue("task.create", "Task to ${a.fullName}: $title") {
                    put("kind", kind); put("title", title); put("description", description); put("assigned_to", a.userId)
                    put("department", a.department); put("priority", priority); if (due.length == 10) put("due_date", due)
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun RequisitionsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.REQUISITIONS, Requisition.serializer()).collectAsState(initial = emptyList())
    AppScreen("Requisitions", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        zw.gov.chipingerdc.shared.ui.TopAction { PrimaryButton("+ New purchase requisition", onClick = { ctx.go(Screen.NewRequisition) }) }
        ListScreen {
            if (list.isEmpty()) item { Empty("No requisitions.") }
            items(list, key = { it.id }) { r ->
                RowCard(r.purpose.take(60), "${r.number} · ${r.departmentLabel} · ${r.requestedByName}", "$${money(r.total)}", r.statusLabel, r.status,
                    r.localNote) { ctx.go(Screen.RequisitionDetail(r.id)) }
            }
        }
    }
}

private class ItemRow(description: String = "", quantity: String = "1", unitCost: String = "") {
    var description by mutableStateOf(description)
    var quantity by mutableStateOf(quantity)
    var unitCost by mutableStateOf(unitCost)
}

/** Any staff member raises a requisition; it then goes HOD → Accountant → Treasurer → CEO (if large). */
@Composable
fun NewRequisitionScreen(ctx: Ctx) {
    val budget by ctx.sdk.observe(Entities.BUDGET_LINES, BudgetLine.serializer()).collectAsState(initial = emptyList())
    val lines = budget.filter { it.kind != "INCOME" && it.department == ctx.me.department }
    var purpose by remember { mutableStateOf("") }
    var line by remember { mutableStateOf<BudgetLine?>(null) }
    val rows = remember { mutableStateListOf(ItemRow()) }
    val total = rows.sumOf { (it.quantity.toDoubleOrNull() ?: 0.0) * (it.unitCost.toDoubleOrNull() ?: 0.0) }
    AppScreen("New requisition", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Purpose / justification", purpose, { purpose = it }, singleLine = false, minLines = 2)
            Picker("Budget vote", lines, line, { "${it.voteCode} ${it.description}" }, { line = it })
            rows.forEachIndexed { i, row ->
                SectionCard("Item ${i + 1}") {
                    Field("Description", row.description, { row.description = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Field("Qty", row.quantity, { row.quantity = it }, Modifier.weight(1f), number = true)
                        Field("Unit cost (USD)", row.unitCost, { row.unitCost = it }, Modifier.weight(1f), number = true)
                    }
                    if (rows.size > 1) SecondaryButton("Remove item", { rows.removeAt(i) })
                }
            }
            SecondaryButton("+ Add item", { rows.add(ItemRow()) })
            Text("Total: USD ${money(total.toString())}", fontSize = 16.sp)
            val valid = purpose.isNotBlank() && rows.all { it.description.isNotBlank() && (it.unitCost.toDoubleOrNull() ?: 0.0) > 0 }
            PrimaryButton("Submit for approval", enabled = valid, onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("number", "(pending)"); put("department", ctx.me.department); put("department_label", ctx.me.departmentLabel)
                    put("requested_by", ctx.me.id); put("requested_by_name", ctx.me.fullName); put("purpose", purpose); put("total", total.toString())
                    put("status", "SUBMITTED"); put("status_label", "Pending sync"); put("updated_at", ctx.sdk.nowIso())
                    put("local_note", "Saved on phone – will be submitted to your HOD on sync")
                }
                ctx.sdk.enqueue("requisition.create", "Requisition: $purpose", Entities.REQUISITIONS, id, optimistic) {
                    put("id", id); put("purpose", purpose); line?.let { put("budget_line", it.id) }; put("submit", true)
                    putJsonArray("items") {
                        rows.forEach { r -> addJsonObject { put("description", r.description); put("quantity", r.quantity); put("unit_cost", r.unitCost) } }
                    }
                }
                ctx.back()
            })
            Text("Workflow: you → Head of Department → Accountant (funds check) → Treasurer → CEO (large amounts) → purchase order.",
                fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}
