package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.BankAccount
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.LeaveRequest
import zw.gov.chipingerdc.shared.model.Payslip
import zw.gov.chipingerdc.shared.model.SalaryProfile
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Message
import zw.gov.chipingerdc.shared.ui.MessageKind
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.money

private fun d(s: String?) = s?.toDoubleOrNull() ?: 0.0

// ================================================================ my profile
/** Everything about me: details, leave days, salary, payslips – what I was paid and what is still owed to me. */
@Composable
fun MyProfileScreen(ctx: Ctx) {
    val me = ctx.me
    val leave by ctx.sdk.observe(Entities.LEAVE, LeaveRequest.serializer()).collectAsState(initial = emptyList())
    val salaries by ctx.sdk.observe(Entities.SALARY_PROFILES, SalaryProfile.serializer()).collectAsState(initial = emptyList())
    val slips by ctx.sdk.observe(Entities.PAYSLIPS, Payslip.serializer()).collectAsState(initial = emptyList())
    val year = Clock.System.now().toLocalDateTime(TimeZone.of("Africa/Harare")).date.year
    val myLeave = leave.filter { it.employee == me.id }
    val annual = myLeave.filter { it.leaveType == "ANNUAL" && it.startDate.startsWith(year.toString()) }
    val taken = annual.filter { it.status == "APPROVED" }.sumOf { it.days }
    val waiting = annual.filter { it.status == "PENDING" }.sumOf { it.days }
    val left = me.annualLeaveDays - taken - waiting
    val salary = salaries.firstOrNull { it.employeeId == me.id }
    val mySlips = slips.filter { it.employeeId == me.id && it.status != "DRAFT" }.sortedWith(compareByDescending<Payslip> { it.year }.thenByDescending { it.month })
    val owed = mySlips.sumOf { d(it.balance) }
    val paidYear = mySlips.filter { it.year == year }.sumOf { d(it.amountPaid) }
    AppScreen("My profile", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            SectionCard("My details") {
                KeyValue("Name", me.fullName)
                KeyValue("Employee no.", me.employeeNumber ?: "—")
                KeyValue("Role", me.roleLabel)
                KeyValue("Department", me.departmentLabel)
                KeyValue("Phone", me.phone.ifBlank { "—" })
                KeyValue("E-mail", me.email.ifBlank { "—" })
                SecondaryButton("Change password", { ctx.go(Screen.ChangePassword) })
            }
            SectionCard("My leave $year") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Kpi("Days a year", me.annualLeaveDays.toString(), null, CrdcColors.Blue, Modifier.weight(1f))
                    Kpi("Taken", taken.toString(), null, CrdcColors.Warning, Modifier.weight(1f))
                    Kpi("Left", left.toString(), if (waiting > 0) "$waiting waiting" else null, CrdcColors.Success, Modifier.weight(1f))
                }
                myLeave.sortedByDescending { it.startDate }.take(5).forEach {
                    RowCard(it.leaveTypeLabel, "${it.startDate} – ${it.endDate} · ${it.days} day(s)", null, it.statusLabel, it.status, it.localNote)
                }
                PrimaryButton("Apply for leave", onClick = { ctx.go(Screen.NewLeave) })
            }
            SectionCard("My salary") {
                if (salary == null) Text("Finance has not set up your salary yet.", fontSize = 13.sp, color = CrdcColors.Muted)
                else {
                    KeyValue("Grade", salary.grade)
                    KeyValue("Basic salary", "${salary.currency} ${money(salary.basicSalary)}")
                    KeyValue("Allowances", money(salary.allowances))
                    KeyValue("Gross", money(salary.gross))
                    KeyValue("Deductions", "− ${money(salary.deductions)} (PAYE ${money(salary.paye)}, NSSA ${money(salary.nssa)}, pension ${money(salary.pension)})")
                    KeyValue("Net pay a month", "${salary.currency} ${money(salary.net)}")
                    KeyValue("Paid into", "${salary.bankName} ${salary.bankAccount}")
                }
            }
            SectionCard("My payslips") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Kpi("Paid to me $year", "$${money(paidYear.toString())}", null, CrdcColors.Success, Modifier.weight(1f))
                    Kpi("Still owed to me", "$${money(owed.toString())}", null, if (owed > 0) CrdcColors.Danger else CrdcColors.Green, Modifier.weight(1f))
                }
                if (mySlips.isEmpty()) Empty("No payslips yet.")
                mySlips.take(12).forEach { s ->
                    RowCard(s.period, "Net ${money(s.net)} · paid ${money(s.amountPaid)}" + if (d(s.balance) > 0) " · owed ${money(s.balance)}" else "",
                        null, s.statusLabel, if (s.status == "APPROVED") "UNPAID" else s.status) { ctx.go(Screen.PayslipDetail(s.id)) }
                }
            }
        }
    }
}

// ================================================================= payroll
@Composable
fun PayrollScreen(ctx: Ctx) {
    val slips by ctx.sdk.observe(Entities.PAYSLIPS, Payslip.serializer()).collectAsState(initial = emptyList())
    val now = Clock.System.now().toLocalDateTime(TimeZone.of("Africa/Harare")).date
    val periods = (slips.map { it.year to it.month } + (now.year to now.monthNumber)).distinct().sortedWith(compareByDescending<Pair<Int, Int>> { it.first }.thenByDescending { it.second })
    var period by remember { mutableStateOf(now.year to now.monthNumber) }
    val list = slips.filter { it.year == period.first && it.month == period.second }.sortedBy { it.employeeName }
    val drafts = list.count { it.status == "DRAFT" }
    AppScreen("Payroll", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item {
                androidx.compose.foundation.layout.Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    ChoicePicker("Month", periods.map { "${it.first}-${it.second}" to monthName(it.first, it.second) }, "${period.first}-${period.second}") { v ->
                        val (y, m) = v.split("-").map { it.toInt() }; period = y to m
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Kpi("Net pay", "$${money(list.sumOf { d(it.net) }.toString())}", "${list.size} staff · $drafts draft", CrdcColors.Blue, Modifier.weight(1f))
                        Kpi("Paid", "$${money(list.sumOf { d(it.amountPaid) }.toString())}", null, CrdcColors.Success, Modifier.weight(1f))
                        Kpi("Owed", "$${money(list.sumOf { d(it.balance) }.toString())}", null, CrdcColors.Danger, Modifier.weight(1f))
                    }
                    if (ctx.me.can("payroll.manage")) PrimaryButton("Prepare payslips for ${monthName(period.first, period.second)}", onClick = {
                        ctx.sdk.enqueue("payroll.run", "Payroll ${period.second}/${period.first}") { put("year", period.first); put("month", period.second) }
                    })
                    if (ctx.me.can("payroll.approve") && drafts > 0) PrimaryButton("Approve $drafts draft payslip(s)", color = CrdcColors.GreenDark, onClick = {
                        ctx.sdk.enqueue("payroll.approve", "Approve payroll ${period.second}/${period.first}") { put("year", period.first); put("month", period.second) }
                    })
                    Text("Prepared by Finance from each salary record · approved by the Treasurer (never by the person who prepared it) · paid in full or in part.",
                        fontSize = 11.sp, color = CrdcColors.Muted)
                }
            }
            if (list.isEmpty()) item { Empty("No payslips for this month yet.") }
            items(list, key = { it.id }) { s ->
                RowCard(s.employeeName, "${Choices.departments.firstOrNull { it.first == s.department }?.second ?: s.department} · net ${money(s.net)} · paid ${money(s.amountPaid)}",
                    if (d(s.balance) > 0) "owes ${money(s.balance)}" else null, s.statusLabel, if (s.status == "APPROVED") "UNPAID" else s.status, s.localNote) { ctx.go(Screen.PayslipDetail(s.id)) }
            }
        }
    }
}

fun monthName(y: Int, m: Int) = listOf("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December").getOrElse(m - 1) { "$m" } + " $y"

@Composable
fun PayslipDetailScreen(ctx: Ctx, id: String) {
    val ps by ctx.sdk.observeOne(Entities.PAYSLIPS, id, Payslip.serializer()).collectAsState(initial = null)
    val banks by ctx.sdk.observe(Entities.BANK_ACCOUNTS, BankAccount.serializer()).collectAsState(initial = emptyList())
    AppScreen("Payslip", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val s = ps ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${s.reference} · ${s.period}") {
                Text(s.employeeName, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                KeyValue("Grade", s.grade)
                KeyValue("Basic salary", money(s.basicSalary))
                KeyValue("Allowances", money(s.allowances))
                KeyValue("Gross pay", "${s.currency} ${money(s.gross)}")
                KeyValue("PAYE", "− ${money(s.paye)}")
                KeyValue("NSSA", "− ${money(s.nssa)}")
                KeyValue("Pension (LAPF)", "− ${money(s.pension)}")
                KeyValue("Medical aid, loans, other", "− ${money(s.otherDeductions)}")
                KeyValue("Net pay", "${s.currency} ${money(s.net)}")
                KeyValue("Paid so far", money(s.amountPaid))
                KeyValue("Still owed", money(s.balance))
                Row { zw.gov.chipingerdc.shared.ui.StatusChip(s.statusLabel, s.status) }
                s.localNote?.let { InfoBox(it) }
            }
            SectionCard("Payments") {
                if (s.payments.isEmpty()) Empty("Nothing paid yet.")
                s.payments.forEach { p -> KeyValue("${p.paidOn} · ${p.method} ${p.reference}", money(p.amount)) }
            }
            if (ctx.me.can("payroll.pay") && s.status in listOf("APPROVED", "PART") && s.employeeId != ctx.me.id && s.localNote == null) {
                ActionPanel("Record a salary payment", listOf(
                    FieldSpec("amount", "Amount (owed ${money(s.balance)})", "number", initial = s.balance),
                    FieldSpec("method", "Method", "choice", listOf("EFT" to "Bank transfer", "CASH" to "Cash", "MOBILE" to "Mobile money")),
                    FieldSpec("bank", "Paid from", "choice", listOf("" to "—") + banks.filter { it.currency == s.currency }.map { it.id to it.name }),
                    FieldSpec("ref", "Bank / transaction reference"),
                ), listOf("pay" to "Record payment"), note = "Part payments are allowed – the balance stays as owed to the employee, who is notified.") { _, v ->
                    ctx.sdk.markPending(Entities.PAYSLIPS, s.id, "Payment queued")
                    ctx.sdk.enqueue("payslip.pay", "Salary ${s.employeeName} ${s.period}", Entities.PAYSLIPS, s.id) {
                        put("payslip", s.id); put("amount", v["amount"] ?: "0"); put("method", v["method"] ?: "EFT"); put("reference", v["ref"] ?: "")
                        v["bank"]?.takeIf { it.isNotBlank() }?.let { put("bank_account", it) }
                    }
                }
            }
        }
    }
}

// ================================================================ salaries
@Composable
fun SalariesScreen(ctx: Ctx) {
    val salaries by ctx.sdk.observe(Entities.SALARY_PROFILES, SalaryProfile.serializer()).collectAsState(initial = emptyList())
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    val missing = staff.filter { s -> s.isActive && salaries.none { it.employeeId == s.userId } }
    AppScreen("Salaries", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { InfoBox("Finance keeps salaries up to date. Every change is in the audit trail; nobody can change their own salary.") }
            items(salaries.sortedBy { it.employeeName }, key = { it.id }) { p ->
                RowCard(p.employeeName, "${p.roleLabel} · grade ${p.grade} · gross ${money(p.gross)} · deductions ${money(p.deductions)}",
                    "${p.currency} ${money(p.net)}", if (p.isActive) null else "Off payroll", "SECONDARY", p.localNote) {
                    if (ctx.me.can("payroll.manage") && p.employeeId != ctx.me.id) ctx.go(Screen.SalaryEdit(p.employeeId))
                }
            }
            if (missing.isNotEmpty() && ctx.me.can("payroll.manage")) {
                item { Text("  Not on the payroll yet", fontSize = 13.sp, color = CrdcColors.Muted) }
                items(missing, key = { "m" + it.id }) { s -> RowCard(s.fullName, s.roleLabel, "Add salary") { if (s.userId != ctx.me.id) ctx.go(Screen.SalaryEdit(s.userId)) } }
            }
        }
    }
}

@Composable
fun SalaryEditScreen(ctx: Ctx, employeeId: Long) {
    val salaries by ctx.sdk.observe(Entities.SALARY_PROFILES, SalaryProfile.serializer()).collectAsState(initial = emptyList())
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    val p = salaries.firstOrNull { it.employeeId == employeeId }
    val name = p?.employeeName ?: staff.firstOrNull { it.userId == employeeId }?.fullName ?: "Employee"
    val keys = listOf("grade" to "Grade / notch", "basic_salary" to "Basic salary", "housing_allowance" to "Housing allowance",
        "transport_allowance" to "Transport allowance", "other_allowances" to "Other allowances", "paye" to "PAYE (from ZIMRA tables)", "nssa" to "NSSA",
        "pension" to "Pension (LAPF)", "medical_aid" to "Medical aid", "other_deductions" to "Loans / union dues / other", "bank_name" to "Bank",
        "bank_account" to "Account / mobile number")
    val values = remember(p?.id) {
        mutableStateMapOf<String, String>().apply {
            put("grade", p?.grade ?: ""); put("basic_salary", p?.basicSalary ?: ""); put("housing_allowance", p?.housingAllowance ?: "")
            put("transport_allowance", p?.transportAllowance ?: ""); put("other_allowances", p?.otherAllowances ?: ""); put("paye", p?.paye ?: "")
            put("nssa", p?.nssa ?: ""); put("pension", p?.pension ?: ""); put("medical_aid", p?.medicalAid ?: "")
            put("other_deductions", p?.otherDeductions ?: ""); put("bank_name", p?.bankName ?: ""); put("bank_account", p?.bankAccount ?: "")
        }
    }
    var saved by remember { mutableStateOf(false) }
    val gross = listOf("basic_salary", "housing_allowance", "transport_allowance", "other_allowances").sumOf { d(values[it]) }
    val ded = listOf("paye", "nssa", "pension", "medical_aid", "other_deductions").sumOf { d(values[it]) }
    AppScreen("Salary – $name", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            keys.forEach { (k, label) -> Field(label, values[k] ?: "", { values[k] = it }, number = k !in listOf("grade", "bank_name", "bank_account")) }
            Text("Gross ${money(gross.toString())} − deductions ${money(ded.toString())} = net ${money((gross - ded).toString())}", fontWeight = FontWeight.SemiBold)
            if (saved) Message("Saved – sent to the server on sync.", MessageKind.SUCCESS)
            PrimaryButton("Save salary", enabled = gross > 0 && gross >= ded, onClick = {
                ctx.sdk.enqueue("salary.update", "Salary $name") {
                    put("employee", employeeId); keys.forEach { (k, _) -> put(k, values[k] ?: "") }
                }
                saved = true
            })
        }
    }
}

@Composable
fun ArrearsScreen(ctx: Ctx) {
    val slips by ctx.sdk.observe(Entities.PAYSLIPS, Payslip.serializer()).collectAsState(initial = emptyList())
    val rows = slips.filter { it.status in listOf("APPROVED", "PART") }.groupBy { it.employeeId }
        .map { (_, l) -> Triple(l.first().employeeName, l.size, l.sumOf { d(it.balance) }) }.sortedByDescending { it.third }
    AppScreen("Salaries owed to staff", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { Kpi("Total owed", "$${money(rows.sumOf { it.third }.toString())}", "${rows.size} people", CrdcColors.Danger, Modifier.fillMaxWidth()) }
            if (rows.isEmpty()) item { Empty("Nobody is owed – all approved salaries are paid.") }
            items(rows, key = { it.first }) { (name, months, owed) -> RowCard(name, "$months month(s) not fully paid", "$${money(owed.toString())}") }
        }
    }
}
