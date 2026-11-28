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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.BudgetLine
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.Requisition
import zw.gov.chipingerdc.shared.model.RevenueHead
import zw.gov.chipingerdc.shared.model.Voucher
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.DecisionPanel
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.Progress
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

// ------------------------------------------------------------------ receipts
@Composable
fun ReceiptFormScreen(ctx: Ctx, accountId: String?, billId: String?) {
    val sdk = ctx.sdk
    val heads by sdk.observe(Entities.REVENUE_HEADS, RevenueHead.serializer()).collectAsState(initial = emptyList())
    var search by remember { mutableStateOf("") }
    val found by sdk.search(Entities.ACCOUNTS, search, ClientAccount.serializer()).collectAsState(initial = emptyList())
    var account by remember { mutableStateOf(accountId?.let { sdk.store.get(Entities.ACCOUNTS, it, ClientAccount.serializer()) }) }
    val bill = remember { billId?.let { sdk.store.get(Entities.BILLS, it, Bill.serializer()) } }
    var head by remember { mutableStateOf<RevenueHead?>(null) }
    if (head == null && heads.isNotEmpty()) head = heads.firstOrNull { it.id == bill?.revenueHead } ?: heads.firstOrNull { it.code == "RATES" }
    var payer by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf(bill?.outstanding ?: "") }
    var currency by remember { mutableStateOf("USD") }
    var method by remember { mutableStateOf("CASH") }
    var reference by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf<String?>(null) }

    AppScreen("Issue receipt", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (done != null) InfoBox(done!!, CrdcColors.Success)
            SectionCard("Payer") {
                if (account == null) {
                    Field("Search account no., name, phone or stand", search, { search = it })
                    if (search.length >= 2) found.take(6).forEach { a ->
                        RowCard(a.name, "${a.accountNumber} · Ward ${a.ward ?: "-"}", "$${money(a.balance)}") { account = a; search = "" }
                    }
                    Field("…or walk-in payer name", payer, { payer = it })
                } else {
                    RowCard(account!!.name, account!!.accountNumber + if (bill != null) " · Bill ${bill.number}" else "", "owes $${money(account!!.balance)}")
                    SecondaryButton("Change payer", { account = null })
                }
            }
            SectionCard("Payment") {
                Picker("Revenue head", heads, head, { "${it.code} – ${it.name}" }, { head = it })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field("Amount", amount, { amount = it }, Modifier.weight(1f), number = true)
                    Row(Modifier.weight(1f)) { ChoicePicker("Currency", Choices.currencies, currency) { currency = it } }
                }
                ChoicePicker("Method", Choices.receiptMethods, method) { method = it }
                if (method != "CASH") Field("Transaction reference", reference, { reference = it })
                Field("Description (optional)", description, { description = it })
            }
            if (error != null) InfoBox(error!!, CrdcColors.Danger)
            PrimaryButton("Issue receipt", onClick = {
                val amt = amount.toDoubleOrNull()
                error = when {
                    head == null -> "Choose a revenue head."
                    amt == null || amt <= 0 -> "Enter a valid amount."
                    account == null && payer.isBlank() -> "Choose an account or enter the payer's name."
                    method != "CASH" && reference.isBlank() -> "Enter the transaction reference for non-cash payments."
                    else -> null
                }
                if (error != null) return@PrimaryButton
                val id = sdk.newId()
                val now = sdk.nowIso()
                val payerName = account?.name ?: payer
                val optimistic = buildJsonObject {
                    put("id", id); put("number", "(pending sync)"); put("payer_name", payerName); put("account", account?.id)
                    put("account_number", account?.accountNumber); put("revenue_head", head!!.id); put("revenue_head_name", head!!.name)
                    put("currency", currency); put("amount", amount); put("method", method); put("reference", reference)
                    put("status", "VALID"); put("status_label", "Pending sync"); put("created_at", now); put("updated_at", now)
                    put("received_by", ctx.me.id); put("local_note", "Captured offline – receipt number issued on sync")
                }
                sdk.enqueue("receipt.create", "Receipt $currency $amount – $payerName", Entities.RECEIPTS, id, optimistic) {
                    put("id", id); put("account", account?.id); put("bill", bill?.id); put("payer_name", payerName)
                    put("revenue_head", head!!.id); put("amount", amount); put("currency", currency); put("method", method)
                    put("reference", reference); put("description", description); put("captured_at", now); put("device_id", sdk.session.deviceId)
                }
                done = "Receipt for $currency $amount saved${if (ctx.sync.online == false) " offline" else ""}. Official number is issued when the phone syncs."
                amount = ""; reference = ""; description = ""; payer = ""; account = null
            })
            Text("Receipts cannot be edited or deleted. Mistakes are corrected through a void request approved by the Accountant.", fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

@Composable
fun ReceiptsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.RECEIPTS, q, Receipt.serializer()).collectAsState(initial = emptyList())
    AppScreen("Receipts", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No receipts on this phone yet.") }
            items(list, key = { it.id }) { r ->
                RowCard(r.number, "${r.payerName} · ${r.revenueHeadName}\n${prettyDate(r.createdAt)} · ${r.methodLabel.ifBlank { r.method }}",
                    "${r.currency} ${money(r.amount)}", r.statusLabel.ifBlank { r.status }, r.status, r.localNote) { ctx.go(Screen.ReceiptDetail(r.id)) }
            }
        }
    }
}

@Composable
fun ReceiptDetailScreen(ctx: Ctx, id: String) {
    val r by ctx.sdk.observeOne(Entities.RECEIPTS, id, Receipt.serializer()).collectAsState(initial = null)
    var reason by remember { mutableStateOf("") }
    AppScreen("Receipt", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val rc = r ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("CHIPINGE RURAL DISTRICT COUNCIL – OFFICIAL RECEIPT") {
                KeyValue("Receipt no.", rc.number)
                KeyValue("Date", prettyDate(rc.offlineCreatedAt ?: rc.createdAt))
                KeyValue("Received from", rc.payerName)
                KeyValue("Account", rc.accountNumber)
                KeyValue("For", rc.revenueHeadName)
                KeyValue("Amount", "${rc.currency} ${money(rc.amount)}")
                KeyValue("Method", "${rc.methodLabel.ifBlank { rc.method }} ${rc.reference}")
                KeyValue("Channel", rc.channelLabel)
                KeyValue("Cashier", rc.receivedByName)
                Row { StatusChip(rc.statusLabel.ifBlank { rc.status }, rc.status) }
                if (rc.localNote != null) InfoBox(rc.localNote!!)
            }
            if (rc.status == "VALID" && rc.localNote == null && ctx.me.can("receipt.void_request", "receipt.void_approve")) {
                SectionCard("Request void") {
                    Field("Reason", reason, { reason = it })
                    PrimaryButton("Request void", enabled = reason.isNotBlank(), color = CrdcColors.Danger, onClick = {
                        ctx.sdk.markPending(Entities.RECEIPTS, rc.id, "Void request queued")
                        ctx.sdk.enqueue("receipt.void_request", "Void ${rc.number}", Entities.RECEIPTS, rc.id) { put("receipt", rc.id); put("reason", reason) }
                    })
                }
            }
            if (rc.status == "VOID_REQ" && rc.localNote == null && ctx.me.can("receipt.void_approve") && rc.voidRequestedBy != ctx.me.id && rc.receivedBy != ctx.me.id) {
                InfoBox("Void requested: ${rc.voidReason}", CrdcColors.Warning)
                DecisionPanel("Void decision", "Approve void") { ok, comment ->
                    ctx.sdk.markPending(Entities.RECEIPTS, rc.id, "Void decision queued")
                    ctx.sdk.enqueue("receipt.void_decide", "Void decision ${rc.number}", Entities.RECEIPTS, rc.id) {
                        put("receipt", rc.id); put("approve", ok); put("comment", comment)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ accounts
@Composable
fun AccountsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.ACCOUNTS, q, ClientAccount.serializer()).collectAsState(initial = emptyList())
    AppScreen("Client accounts", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search account no., name, phone, ID", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No accounts found.") }
            items(list, key = { it.id }) { a ->
                RowCard(a.name, "${a.accountNumber} · ${a.accountTypeLabel} · Ward ${a.ward ?: "-"} · ${a.phone}", "$${money(a.balance)}",
                    a.statusLabel, a.status) { ctx.go(Screen.AccountDetail(a.id)) }
            }
        }
    }
}

@Composable
fun AccountDetailScreen(ctx: Ctx, id: String) {
    val sdk = ctx.sdk
    val a by sdk.observeOne(Entities.ACCOUNTS, id, ClientAccount.serializer()).collectAsState(initial = null)
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val receipts by sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    AppScreen("Account", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val acc = a ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(acc.name) {
                KeyValue("Account no.", acc.accountNumber)
                KeyValue("Type", acc.accountTypeLabel)
                KeyValue("Phone", acc.phone)
                KeyValue("ID / Reg no.", acc.idNumber)
                KeyValue("Ward", acc.ward?.toString())
                KeyValue("Balance owed", "USD ${money(acc.balance)}")
            }
            if (ctx.me.can("receipt.create")) PrimaryButton("Receive payment", onClick = { ctx.go(Screen.NewReceiptFor(acc.id, null)) })
            SectionCard("Properties / stands") {
                props.filter { it.account == acc.id }.forEach {
                    RowCard(if (it.hectares != null) "Farm ${it.standNumber}" else "Stand ${it.standNumber}",
                        if (it.hectares != null) "${it.location} · ${it.hectares} ha" else "${it.location} · ${it.landUseLabel} · $${money(it.monthlyRates)}/month",
                        null, null, null) { ctx.go(Screen.StandRecord(it.id)) }
                }
            }
            SectionCard("Unpaid / recent bills") {
                val mine = bills.filter { it.account == acc.id }
                if (mine.isEmpty()) Text("No bills", color = CrdcColors.Muted)
                mine.forEach { b ->
                    RowCard(b.description, "${b.number} · due ${prettyDate(b.dueDate)}", "$${money(b.outstanding)}", b.statusLabel, b.status,
                        onClick = if (ctx.me.can("receipt.create") && b.status in listOf("UNPAID", "PART")) ({ ctx.go(Screen.NewReceiptFor(acc.id, b.id)) }) else null)
                }
            }
            SectionCard("Payments") {
                receipts.filter { it.account == acc.id }.take(20).forEach { r ->
                    RowCard(r.number, prettyDate(r.createdAt), "${r.currency} ${money(r.amount)}", r.statusLabel, r.status, r.localNote) { ctx.go(Screen.ReceiptDetail(r.id)) }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ licences
@Composable
fun LicencesScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.LICENCES, q, Licence.serializer()).collectAsState(initial = emptyList())
    AppScreen(if (ctx.me.can("licence.view")) "Licences" else "Shop health inspections", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search business, number, premises", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No licences.") }
            items(list, key = { it.id }) { l ->
                RowCard(l.businessName, "${l.number} · ${l.licenceTypeLabel}\n${l.premises}", "$${money(l.fee)}", l.statusLabel, l.status, l.localNote) {
                    ctx.go(Screen.LicenceDetail(l.id))
                }
            }
        }
    }
}

@Composable
fun LicenceDetailScreen(ctx: Ctx, id: String) {
    val l by ctx.sdk.observeOne(Entities.LICENCES, id, Licence.serializer()).collectAsState(initial = null)
    var notes by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }
    AppScreen("Licence", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val lic = l ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${lic.licenceTypeLabel} – ${lic.number}") {
                KeyValue("Business", lic.businessName)
                KeyValue("Activity", lic.businessActivity)
                KeyValue("Premises", lic.premises)
                KeyValue("Account", lic.accountNumber)
                KeyValue("Fee", "USD ${money(lic.fee)}")
                KeyValue("Inspection", lic.inspectionNotes)
                KeyValue("Process by", prettyDate(lic.dueAt))
                KeyValue("Valid", if (lic.issueDate != null) "${prettyDate(lic.issueDate)} – ${prettyDate(lic.expiryDate)}" else null)
                Row { StatusChip(lic.statusLabel, lic.status) }
                if (lic.localNote != null) InfoBox(lic.localNote!!)
            }
            if (lic.stillToPay.isNotEmpty()) SectionCard("Still to pay") {
                lic.stillToPay.forEach { KeyValue(it.label, "USD ${money(it.amount)}") }
                InfoBox("No approvals needed: the licence is issued automatically as soon as everything is paid.")
                if (ctx.me.can("receipt.create") && lic.bill != null) PrimaryButton("Receive payment", onClick = { ctx.go(Screen.NewReceiptFor(lic.account, lic.bill)) })
            }
            when (licenceStage(ctx.me, lic)) {
                "Inspection" -> SectionCard("Premises inspection") {
                    Field("Inspection findings", notes, { notes = it }, singleLine = false, minLines = 3)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.weight(1f)) {
                            PrimaryButton("Passed", enabled = notes.isNotBlank(), onClick = { inspect(ctx, lic, true, notes) })
                        }
                        Row(Modifier.weight(1f)) {
                            PrimaryButton("Failed", enabled = notes.isNotBlank(), color = CrdcColors.Danger, onClick = { inspect(ctx, lic, false, notes) })
                        }
                    }
                }
                "Approval" -> {
                    Field("Licence fee (USD) – leave blank for default ${lic.fee}", fee, { fee = it }, number = true)
                    DecisionPanel("Licence decision") { ok, comment ->
                        ctx.sdk.markPending(Entities.LICENCES, lic.id, "Decision queued")
                        ctx.sdk.enqueue("licence.decide", "Licence ${lic.number} decision", Entities.LICENCES, lic.id) {
                            put("licence", lic.id); put("approve", ok); put("comment", comment); if (fee.isNotBlank()) put("fee", fee)
                        }
                    }
                }
                else -> Unit
            }
        }
    }
}

private fun inspect(ctx: Ctx, lic: Licence, passed: Boolean, notes: String) {
    ctx.sdk.markPending(Entities.LICENCES, lic.id, "Inspection result queued")
    ctx.sdk.enqueue("licence.inspect", "Inspection ${lic.number}", Entities.LICENCES, lic.id) {
        put("licence", lic.id); put("passed", passed); put("notes", notes)
    }
}

// ----------------------------------------------------------------- approvals
@Composable
fun ApprovalsScreen(ctx: Ctx) {
    val approvals = rememberApprovals(ctx)
    var leaveOpen by remember { mutableStateOf<String?>(null) }
    AppScreen("Waiting for my action", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (approvals.isEmpty()) item { Empty("Nothing waiting for you.") }
            items(approvals, key = { it.kind + it.ref + it.text }) { a ->
                if (a.leave != null && leaveOpen == a.leave.id) {
                    DecisionPanel("Leave: ${a.leave.employeeName} – ${a.text}") { ok, comment ->
                        ctx.sdk.markPending(Entities.LEAVE, a.leave.id, "Decision queued")
                        ctx.sdk.enqueue("leave.decide", "Leave decision ${a.leave.employeeName}", Entities.LEAVE, a.leave.id) {
                            put("leave", a.leave.id); put("approve", ok); put("comment", comment)
                        }
                        leaveOpen = null
                    }
                } else {
                    RowCard("${a.kind}: ${a.ref}", a.text, null, a.stage, "PENDING") {
                        if (a.screen != null) ctx.go(a.screen) else leaveOpen = a.leave?.id
                    }
                }
            }
        }
    }
}

@Composable
fun RequisitionDetailScreen(ctx: Ctx, id: String) {
    val r by ctx.sdk.observeOne(Entities.REQUISITIONS, id, Requisition.serializer()).collectAsState(initial = null)
    AppScreen("Requisition", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val req = r ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(req.number) {
                KeyValue("Department", req.departmentLabel)
                KeyValue("Requested by", req.requestedByName)
                KeyValue("Purpose", req.purpose)
                KeyValue("Total", "USD ${money(req.total)}")
                KeyValue("CEO authorisation", if (req.needsCeo) "Required" else "Not required")
                Row { StatusChip(req.statusLabel, req.status) }
                if (req.localNote != null) InfoBox(req.localNote!!)
            }
            SectionCard("Items") {
                req.items.forEach { KeyValue("${it.quantity} × ${it.description}", "$${money(it.total)}") }
            }
            requisitionStage(ctx.me, req)?.let { stage ->
                DecisionPanel("Your decision: $stage") { ok, comment ->
                    ctx.sdk.markPending(Entities.REQUISITIONS, req.id, "Decision queued")
                    ctx.sdk.enqueue("requisition.decide", "Requisition ${req.number}: ${if (ok) "approve" else "reject"}", Entities.REQUISITIONS, req.id) {
                        put("requisition", req.id); put("approve", ok); put("comment", comment)
                    }
                }
            }
            IssueOrderPanel(ctx, req)
        }
    }
}

@Composable
fun VoucherDetailScreen(ctx: Ctx, id: String) {
    val v by ctx.sdk.observeOne(Entities.VOUCHERS, id, Voucher.serializer()).collectAsState(initial = null)
    AppScreen("Payment voucher", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val pv = v ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(pv.number) {
                KeyValue("Payee", pv.payeeName)
                KeyValue("Category", pv.categoryLabel)
                KeyValue("Description", pv.description)
                KeyValue("Invoice", pv.invoiceNumber)
                KeyValue("Budget vote", pv.vote)
                KeyValue("Amount", "${pv.currency} ${money(pv.amount)}")
                KeyValue("USD equivalent", money(pv.baseAmount))
                KeyValue("Method", pv.methodLabel)
                KeyValue("Prepared by", pv.preparedByName)
                KeyValue("CEO authorisation", if (pv.needsCeo) "Required" else "Not required")
                KeyValue("Paid", pv.paidAt?.let { "${prettyDate(it)} · ${pv.paymentReference}" })
                Row { StatusChip(pv.statusLabel, pv.status) }
                if (pv.localNote != null) InfoBox(pv.localNote!!)
            }
            voucherStage(ctx.me, pv)?.let { stage ->
                DecisionPanel("Your decision: $stage") { ok, comment ->
                    ctx.sdk.markPending(Entities.VOUCHERS, pv.id, "Decision queued")
                    ctx.sdk.enqueue("voucher.decide", "Voucher ${pv.number}: ${if (ok) "approve" else "reject"}", Entities.VOUCHERS, pv.id) {
                        put("voucher", pv.id); put("approve", ok); put("comment", comment)
                    }
                }
            }
            VoucherPayPanel(ctx, pv)
        }
    }
}

@Composable
fun BudgetScreen(ctx: Ctx) {
    val lines by ctx.sdk.observe(Entities.BUDGET_LINES, BudgetLine.serializer()).collectAsState(initial = emptyList())
    AppScreen("Budget vs actual", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (lines.isEmpty()) item { Empty("No budget lines synced.") }
            items(lines.sortedBy { it.voteCode }, key = { it.id }) { b ->
                val budget = (b.revisedAmount ?: b.approvedAmount).toDoubleOrNull() ?: 0.0
                val used = (b.actual.toDoubleOrNull() ?: 0.0) + (b.committed.toDoubleOrNull() ?: 0.0)
                val pct = if (budget > 0) (used / budget * 100).toInt() else 0
                SectionCard("${b.voteCode} ${b.description}") {
                    Text("${b.kindLabel} · ${b.department}", fontSize = 12.sp, color = CrdcColors.Muted)
                    KeyValue("Budget", "$${money(budget.toString())}")
                    KeyValue(if (b.kind == "INCOME") "Collected" else "Spent", "$${money(b.actual)}")
                    if (b.kind != "INCOME") KeyValue("Committed", "$${money(b.committed)}")
                    Progress(pct)
                    Text("$pct% used", fontSize = 11.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
                        color = if (pct > 100) CrdcColors.Danger else CrdcColors.Muted, modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
}
