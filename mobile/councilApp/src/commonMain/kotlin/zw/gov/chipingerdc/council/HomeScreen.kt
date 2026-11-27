package zw.gov.chipingerdc.council

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
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
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.FundsRequest
import zw.gov.chipingerdc.shared.model.Memo
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.ServiceRequest
import zw.gov.chipingerdc.shared.model.Task
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.IndexModule
import zw.gov.chipingerdc.shared.ui.IndexRow
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.LocalSiteName
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.isPast
import zw.gov.chipingerdc.shared.ui.money

private data class Tile(val label: String, val screen: Screen, val badge: Int = 0, val add: Screen? = null)

/**
 * The menu: the person's own department (its daily work and its registers in one list),
 * customer care when the person handles complaints, and governance. Personal things –
 * profile, leave, payslips, notifications – are under the profile icon, not here.
 * The CEO and Internal Audit get one section per department.
 */
@Composable
fun CouncilMenu(ctx: Ctx) {
    val me = ctx.me
    val sdk = ctx.sdk
    val tasks by sdk.observe(Entities.TASKS, Task.serializer()).collectAsState(initial = emptyList())
    val complaints by sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    val requests by sdk.observe(Entities.SERVICE_REQUESTS, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    val funds by sdk.observe(Entities.FUNDS_REQUESTS, FundsRequest.serializer()).collectAsState(initial = emptyList())
    val memos by sdk.observe(Entities.MEMOS, Memo.serializer()).collectAsState(initial = emptyList())
    val approvals = rememberApprovals(ctx)
    val seesAll = me.isCeo || me.can("audit.view_all")

    val myTasks = tasks.count { it.assignedToName == me.fullName && it.status in listOf("OPEN", "IN_PROGRESS") }
    val unacked = complaints.count { it.status !in listOf("RESOLVED", "CLOSED") && it.acknowledgedAt == null }
    val overdueFaults = requests.count { it.status !in listOf("RESOLVED", "CLOSED", "REJECTED") && isPast(it.dueAt) }
    val myFunds = funds.count { it.requestedBy == me.id && (it.isOpen || it.status == "RETURNED") }
    val newMemos = memos.count { it.sender != me.id && it.status == "SENT" }

    val work = buildList {
        add(Tile("Dashboard", Screen.Home))
        if (me.can("reports.executive")) add(Tile("Executive overview", Screen.Executive))
        if (me.can("dept.overview", "dept.overview_all")) add(Tile("Department overview", Screen.Department()))
        add(Tile("Tasks", Screen.Tasks, myTasks, if (me.can("tasks.assign_any", "tasks.assign_department")) Screen.NewTask else null))
        add(Tile("Memos to / from departments", Screen.Memos, newMemos, Screen.NewMemo))
        if (me.can("funds.request")) add(Tile("Requests for funds & purchases", Screen.Funds, myFunds, Screen.NewFunds))
        if (me.can("requisition.create")) add(Tile("Purchase requisitions", Screen.Requisitions, add = Screen.NewRequisition))
        add(Tile("Service requests / faults", Screen.Requests, overdueFaults, Screen.NewRequest))
        add(Tile("ICT support", Screen.Tickets, add = Screen.NewTicket))
        if (me.can("leave.approve")) add(Tile("Leave applications to approve", Screen.Leave))
        if (me.can("resolutions.update") && !me.can("meetings.view")) add(Tile("Council resolutions for the department", Screen.Resolutions))
    }
    val finance = buildList {
        if (me.can("finance.view")) add(Tile("Receipts", Screen.Receipts, add = if (me.can("receipt.create")) Screen.NewReceipt else null))
        if (me.can("cashup.submit", "cashup.verify")) add(Tile("Cash-ups", Screen.CashUps))
        if (me.can("accounts.manage", "finance.view_all", "receipt.create")) add(Tile("Client accounts", Screen.Accounts))
        if (me.can("areas.view", "accounts.manage")) add(Tile("Areas overview – shops paid / owing", Screen.Areas))
        if (me.can("claims.review")) add(Tile("Stand registrations", Screen.Claims))
        if (me.can("leases.view", "leases.manage")) add(Tile("Leases", Screen.Leases))
        if (me.can("licence.view")) add(Tile("Licences", Screen.Licences, add = if (me.can("licence.manage")) Screen.NewLicence else null))
        if (me.can("voucher.prepare", "voucher.check", "voucher.approve", "voucher.authorise", "voucher.pay", "finance.view_all"))
            add(Tile("Payment vouchers", Screen.Vouchers, add = if (me.can("voucher.prepare")) Screen.NewVoucher(null) else null))
        if (me.can("payroll.view", "payroll.manage")) {
            add(Tile("Payroll", Screen.Payroll)); add(Tile("Salaries", Screen.Salaries)); add(Tile("Salaries owed to staff", Screen.Arrears))
            add(Tile("PAYE tax tables", Screen.TaxTables))
        }
        if (me.can("budget.view")) add(Tile("Budget vs actual", Screen.Budget))
        if (me.can("finance.reports", "reports.executive")) add(Tile("Financial reports", Screen.FinanceReport))
        if (me.can("procurement.order", "finance.view_all")) add(Tile("Purchase orders", Screen.Orders))
        if (me.can("fines.view")) add(Tile("Fines & penalties", Screen.Register("fines"), add = if (me.can("fines.issue")) Screen.NewFine else null))
        if (me.department != "SOCIAL") {
            if (me.can("hunts.view")) add(Tile("CAMPFIRE trophy fees", Screen.Register("trophy_hunts")))
            if (me.can("permits.view")) add(Tile("Sand, mining & forestry permits", Screen.Register("resource_permits")))
            if (me.can("farms.view")) add(Tile("Farms register (farm levy)", Screen.Register("farms")))
        }
    }
    val admin = buildList {
        if (me.can("meetings.view")) { add(Tile("Council meetings", Screen.Meetings)); add(Tile("Resolutions", Screen.Resolutions)) }
        if (me.can("policies.view")) add(Tile("Policies & by-laws", Screen.Policies))
        if (me.can("correspondence.manage") || me.isHead) add(Tile("Correspondence", Screen.Correspondence, add = Screen.NewCorrespondence))
        if (me.can("hr.view")) add(Tile("Staff directory", Screen.Staff))
        if (me.department == "ADMIN" && me.can("activities.manage")) add(Tile("Trainings & staff activities", Screen.Activities, add = Screen.NewActivity))
        if (!me.can("finance.view") && me.can("procurement.order")) add(Tile("Purchase orders", Screen.Orders))
    }
    val social = buildList {
        if (me.can("stands.view")) add(Tile("Stand applications", Screen.Stands, add = if (me.can("stands.manage")) Screen.NewStand else null))
        if (me.can("incidents.view")) add(Tile("Incidents & disasters", Screen.Incidents, add = if (me.can("incidents.manage")) Screen.NewIncident else null))
        if ((me.department == "SOCIAL" || seesAll) && me.can("activities.manage", "activities.verify", "dept.overview_all"))
            add(Tile("Community programmes", Screen.Activities, add = if (me.can("activities.manage")) Screen.NewActivity else null))
        if (me.can("licence.inspect")) add(Tile("Health certificate inspections", Screen.Licences))
        if (me.can("welfare.view", "welfare.manage")) add(Tile("Social welfare – vulnerable households", Screen.Register("beneficiaries"),
            add = if (me.can("welfare.manage")) Screen.RegisterForm("beneficiaries", null) else null))
        if (me.can("water.view", "water.manage")) add(Tile("Water points (WASH)", Screen.Register("water_points"),
            add = if (me.can("water.manage")) Screen.RegisterForm("water_points", null) else null))
        // CAMPFIRE
        if (me.can("wildlife.view", "wildlife.manage")) add(Tile("CAMPFIRE – wildlife database", Screen.Register("wildlife"),
            add = if (me.can("wildlife.manage")) Screen.RegisterForm("wildlife", null) else null))
        if (me.can("hunts.view", "hunts.manage")) {
            add(Tile("CAMPFIRE – hunting quotas", Screen.Register("hunting_quotas"), add = if (me.can("hunts.manage")) Screen.RegisterForm("hunting_quotas", null) else null))
            add(Tile("CAMPFIRE – trophy hunts", Screen.Register("trophy_hunts"), add = if (me.can("hunts.manage")) Screen.NewHunt else null))
        }
        // natural resources & agriculture
        if (me.can("permits.view", "permits.manage")) add(Tile("Sand, mining & forestry permits", Screen.Register("resource_permits"),
            add = if (me.can("permits.manage")) Screen.RegisterForm("resource_permits", null) else null))
        if (me.can("farms.view", "farms.manage")) add(Tile("Agricultural farms", Screen.Register("farms"),
            add = if (me.can("farms.manage")) Screen.RegisterForm("farms", null) else null))
    }
    val tech = buildList {
        if (me.can("projects.view")) add(Tile("Projects", Screen.Projects))
        if (me.can("plans.view")) add(Tile("Building plans", Screen.Plans))
    }
    val audit = buildList {
        if (me.can("audit.findings_view", "audit.respond")) add(Tile("Audit findings", Screen.Findings))
        if (me.can("risks.view", "risks.manage")) add(Tile("Risk register", Screen.Risks))
    }
    val assets = if (me.can("assets.view")) listOf(Tile(if (me.can("assets.manage") || seesAll) "Assets & infrastructure" else "Department assets", Screen.Assets)) else emptyList()

    val byDept = mapOf("FINANCE" to finance, "ADMIN" to admin, "SOCIAL" to social, "TECH" to tech, "AUDIT" to audit)
    val sections = buildList {
        if (seesAll) {
            add(me.departmentLabel to work)
            listOf("FINANCE" to "Finance", "ADMIN" to "Administration", "SOCIAL" to "Social Services", "TECH" to "Technical Services", "AUDIT" to "Internal Audit")
                .forEach { (code, label) -> add(label to (byDept[code] ?: emptyList()) + if (code == "ADMIN") assets else emptyList()) }
        } else {
            // own department: day-to-day work + its registers in one list
            add(me.departmentLabel to work + (byDept[me.department] ?: emptyList()) + assets + audit.takeIf { me.department != "AUDIT" }.orEmpty())
        }
        if (me.can("complaints.view_all", "complaints.manage", "complaints.department") || complaints.isNotEmpty())
            add("Customer care" to listOf(Tile(if (me.can("complaints.view_all", "complaints.manage", "complaints.department")) "Complaints, compliments & suggestions"
                else "Complaints given to me", Screen.Complaints, unacked, if (me.can("complaints.manage", "complaints.department", "complaints.view_all")) Screen.NewComplaint else null)))
        if (me.can("fines.issue") && me.department != "FINANCE" && !seesAll)
            add("By-law enforcement" to listOf(Tile("Fines I have issued", Screen.Register("fines"), add = Screen.NewFine)))
        if (me.can("audit.view_trail")) add("Governance" to listOf(Tile("Audit trail", Screen.AuditTrail)))
    }.filter { it.second.isNotEmpty() }

    Column(Modifier.fillMaxSize().background(Color.White).verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        sections.forEach { (title, tiles) ->
            IndexModule(title, tiles.map { t -> IndexRow(t.label, t.badge, { ctx.go(t.screen) }, t.add?.let { a -> { ctx.go(a) } }) })
        }
    }
}

/** What a person sees after logging in: their dashboard. The menu opens from the menu icon. */
@Composable
fun HomeScreen(ctx: Ctx) {
    val me = ctx.me
    val sdk = ctx.sdk
    val receipts by sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    val tasks by sdk.observe(Entities.TASKS, Task.serializer()).collectAsState(initial = emptyList())
    val complaints by sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    val requests by sdk.observe(Entities.SERVICE_REQUESTS, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    val funds by sdk.observe(Entities.FUNDS_REQUESTS, FundsRequest.serializer()).collectAsState(initial = emptyList())
    val approvals = rememberApprovals(ctx)
    val today = Clock.System.now().toLocalDateTime(TimeZone.of("Africa/Harare")).date.toString()
    val myToday = receipts.filter { it.createdAt.startsWith(today) && it.status != "VOIDED" && (it.receivedBy == me.id || it.localNote != null) }
    val myTasks = tasks.filter { it.assignedToName == me.fullName && it.status in listOf("OPEN", "IN_PROGRESS") }
    val openFaults = requests.filter { it.status !in listOf("RESOLVED", "CLOSED", "REJECTED") }
    val openComplaints = complaints.filter { it.status !in listOf("RESOLVED", "CLOSED") }
    val myFunds = funds.filter { it.requestedBy == me.id && (it.isOpen || it.status == "RETURNED") }

    AppScreen("Dashboard", sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Text(me.departmentLabel, fontSize = 13.sp, color = CrdcColors.Muted)
            // 1. key figures – only facts that are not listed again below
            val figures = buildList<@Composable (Modifier) -> Unit> {
                if (me.can("finance.view_all")) add { m ->
                    val all = receipts.filter { it.createdAt.startsWith(today) && it.status != "VOIDED" }
                    val usd = all.filter { it.currency == "USD" }.sumOf { it.amount.toDoubleOrNull() ?: 0.0 }
                    Kpi("Council collected today", "$${money(usd.toString())}", "${all.size} receipt(s)", CrdcColors.Success, m) { ctx.go(Screen.Receipts) }
                } else if (me.can("receipt.create")) add { m ->
                    val usd = myToday.filter { it.currency == "USD" }.sumOf { it.amount.toDoubleOrNull() ?: 0.0 }
                    Kpi("My collections today", "$${money(usd.toString())}", "${myToday.size} receipt(s)", modifier = m) { ctx.go(Screen.Receipts) }
                }
                add { m -> Kpi("Faults / service requests", openFaults.size.toString(), "${openFaults.count { isPast(it.dueAt) }} overdue", CrdcColors.Blue, m) { ctx.go(Screen.Requests) } }
                if (me.can("complaints.view_all", "complaints.manage", "complaints.department") || openComplaints.isNotEmpty()) add { m ->
                    Kpi("Complaints to handle", openComplaints.size.toString(), "${openComplaints.count { it.acknowledgedAt == null }} not acknowledged", CrdcColors.Danger, m) { ctx.go(Screen.Complaints) }
                }
            }
            figures.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) { row.forEach { it(Modifier.weight(1f)) } }
            }
            // 2. what needs me – each list shows its own count
            SectionCard("Waiting for my approval (${approvals.size})") {
                if (approvals.isEmpty()) Empty("Nothing waiting for you.")
                approvals.take(5).forEach { a -> RowCard(a.ref, "${a.kind} · ${a.text}", null, a.stage, "PENDING") { a.screen?.let(ctx::go) ?: ctx.go(Screen.Approvals) } }
                if (approvals.size > 5) Text("See all ${approvals.size} ›", color = CrdcColors.Blue, fontSize = 13.sp,
                    modifier = Modifier.padding(8.dp).clickable { ctx.go(Screen.Approvals) })
            }
            SectionCard("My tasks (${myTasks.size})") {
                if (myTasks.isEmpty()) Empty("No open tasks.")
                myTasks.take(4).forEach { t -> RowCard(t.title, "${t.reference} · due ${t.dueDate ?: "-"} · from ${t.assignedByName}", null, t.statusLabel, t.status) { ctx.go(Screen.TaskDetail(t.id)) } }
            }
            if (myFunds.isNotEmpty()) SectionCard("My requests for funds & purchases (${myFunds.size})") {
                myFunds.forEach { r -> RowCard(r.title, "Now: ${r.whereNow}", "${r.currency} ${money(r.total)}", r.statusLabel, r.status, r.localNote) { ctx.go(Screen.FundsDetail(r.id)) } }
            }
        }
    }
}
