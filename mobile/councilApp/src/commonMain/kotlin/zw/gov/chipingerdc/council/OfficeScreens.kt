package zw.gov.chipingerdc.council

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.BankAccount
import zw.gov.chipingerdc.shared.model.BudgetLine
import zw.gov.chipingerdc.shared.model.CashUp
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Correspondence
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.PurchaseOrder
import zw.gov.chipingerdc.shared.model.Requisition
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.model.Supplier
import zw.gov.chipingerdc.shared.model.Voucher
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
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.bottomRule
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

// =========================================================== payment vouchers
@Composable
fun VouchersScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.VOUCHERS, Voucher.serializer()).collectAsState(initial = emptyList())
    var show by remember { mutableStateOf("OPEN") }
    val shown = when (show) {
        "OPEN" -> list.filter { it.status in listOf("PREPARED", "CHECKED", "APPROVED", "AUTHORISED") }
        "PAID" -> list.filter { it.status == "PAID" }
        else -> list
    }
    AppScreen("Payment vouchers", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("voucher.prepare")) PrimaryButton("+ Prepare payment voucher", onClick = { ctx.go(Screen.NewVoucher(null)) })
        Tabs(listOf("OPEN" to "In approval / to pay", "PAID" to "Paid", "ALL" to "All"), show) { show = it }
        ListScreen {
            if (shown.isEmpty()) item { Empty("No vouchers.") }
            items(shown, key = { it.id }) { v ->
                RowCard(v.payeeName, "${v.number} · ${v.categoryLabel} · ${v.description.take(50)}", "${v.currency} ${money(v.amount)}", v.statusLabel,
                    v.status, v.localNote) { ctx.go(Screen.VoucherDetail(v.id)) }
            }
        }
    }
}

fun voucherReady(v: Voucher) = v.status == "AUTHORISED" || (v.status == "APPROVED" && !v.needsCeo)

/** Pay an approved voucher from the phone / desktop (bank account + cheque / RTGS reference). */
@Composable
fun VoucherPayPanel(ctx: Ctx, v: Voucher) {
    val banks by ctx.sdk.observe(Entities.BANK_ACCOUNTS, BankAccount.serializer()).collectAsState(initial = emptyList())
    val usable = banks.filter { it.currency == v.currency && it.isActive }
    if (!voucherReady(v) || !ctx.me.can("voucher.pay") || v.localNote != null) return
    ActionPanel("Pay this voucher", listOf(
        FieldSpec("bank", "Pay from", "choice", usable.map { it.id to "${it.name} · balance ${it.currency} ${money(it.balance)}" }),
        FieldSpec("ref", "Cheque / RTGS / transaction reference"),
    ), listOf("pay" to "Record payment"), note = "The bank balance is checked by the server; the requester or supplier is notified.") { _, vals ->
        ctx.sdk.markPending(Entities.VOUCHERS, v.id, "Payment queued")
        ctx.sdk.enqueue("voucher.pay", "Pay ${v.number}", Entities.VOUCHERS, v.id) {
            put("voucher", v.id); put("bank_account", vals["bank"] ?: ""); put("payment_reference", vals["ref"] ?: "")
        }
    }
}

@Composable
fun NewVoucherScreen(ctx: Ctx, poId: String?) {
    val suppliers by ctx.sdk.observe(Entities.SUPPLIERS, Supplier.serializer()).collectAsState(initial = emptyList())
    val orders by ctx.sdk.observe(Entities.PURCHASE_ORDERS, PurchaseOrder.serializer()).collectAsState(initial = emptyList())
    val budget by ctx.sdk.observe(Entities.BUDGET_LINES, BudgetLine.serializer()).collectAsState(initial = emptyList())
    val po = orders.firstOrNull { it.id == poId }
    var supplier by remember { mutableStateOf<Supplier?>(null) }
    var payee by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("SUPPLIER") }
    var description by remember(po) { mutableStateOf(po?.let { "${it.number}: ${it.requisitionPurpose}" } ?: "") }
    var amount by remember(po) { mutableStateOf(po?.amount ?: "") }
    var currency by remember { mutableStateOf("USD") }
    var method by remember { mutableStateOf("EFT") }
    var invoice by remember { mutableStateOf("") }
    var vote by remember { mutableStateOf<BudgetLine?>(null) }
    if (po != null && supplier == null) supplier = suppliers.firstOrNull { it.id == po.supplier }
    AppScreen("Prepare payment voucher", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            InfoBox("Goes to the Accountant (check), the Treasurer (approval) and the CEO if large, before it can be paid. You cannot approve a voucher you prepared.")
            po?.let { KeyValue("Purchase order", "${it.number} · ${it.supplierName} · goods received") }
            ChoicePicker("Category", Choices.voucherCategories, category) { category = it }
            Picker("Supplier (blank for other payees)", suppliers.filter { it.status == "ACTIVE" }, supplier, { "${it.name} · ${it.category}" }, { supplier = it })
            if (supplier == null) Field("Payee name", payee, { payee = it })
            Field("Description", description, { description = it }, singleLine = false, minLines = 2)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Field("Amount", amount, { amount = it }, Modifier.weight(1f), number = true)
                Column(Modifier.weight(1f)) { ChoicePicker("Currency", Choices.currencies, currency) { currency = it } }
            }
            ChoicePicker("Payment method", Choices.voucherMethods, method) { method = it }
            Field("Supplier invoice no.", invoice, { invoice = it })
            Picker("Budget vote", budget.filter { it.kind != "INCOME" }, vote, { "${it.voteCode} ${it.description}" }, { vote = it })
            val ok = description.isNotBlank() && (amount.toDoubleOrNull() ?: 0.0) > 0 && (supplier != null || payee.isNotBlank())
            PrimaryButton("Save voucher – send for checking", enabled = ok, onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("number", "(pending)"); put("payee_name", supplier?.name ?: payee); put("description", description)
                    put("amount", amount); put("currency", currency); put("status", "PREPARED"); put("status_label", "Pending sync")
                    put("category_label", Choices.voucherCategories.first { it.first == category }.second); put("prepared_by", ctx.me.id)
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved – sent to the Accountant on sync")
                }
                ctx.sdk.enqueue("voucher.prepare", "Voucher: ${supplier?.name ?: payee}", Entities.VOUCHERS, id, optimistic) {
                    put("id", id); put("category", category); put("description", description); put("amount", amount); put("currency", currency)
                    put("method", method); put("invoice_number", invoice); supplier?.let { put("supplier", it.id) }
                    if (supplier == null) put("payee_name", payee)
                    vote?.let { put("budget_line", it.id) }; po?.let { put("purchase_order", it.id) }
                }
                ctx.back()
            })
        }
    }
}

// =================================================================== cash-ups
@Composable
fun CashUpsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.CASHUPS, CashUp.serializer()).collectAsState(initial = emptyList())
    var declared by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var currency by remember { mutableStateOf("USD") }
    var sent by remember { mutableStateOf(false) }
    AppScreen("Cash-ups", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (ctx.me.can("cashup.submit")) item {
                SectionCard("End of day: declare my cash") {
                    Text("Count the cash in your drawer. The server compares it with every cash receipt you issued since your last cash-up " +
                        "(including receipts issued offline on this device).", fontSize = 12.sp, color = CrdcColors.Muted)
                    ChoicePicker("Currency", Choices.currencies, currency) { currency = it }
                    Field("Cash counted", declared, { declared = it }, number = true)
                    Field("Notes (optional)", notes, { notes = it })
                    if (sent) Message("Cash-up queued – the Accountant verifies it.", MessageKind.SUCCESS)
                    PrimaryButton("Submit cash-up", enabled = (declared.toDoubleOrNull() ?: -1.0) >= 0, onClick = {
                        ctx.sdk.enqueue("cashup.submit", "Cash-up $currency $declared") {
                            put("currency", currency); put("declared_cash", declared); put("notes", notes)
                        }
                        declared = ""; notes = ""; sent = true
                    })
                }
            }
            if (list.isEmpty()) item { Empty("No cash-ups yet.") }
            items(list, key = { it.id }) { c ->
                val v = c.variance.toDoubleOrNull() ?: 0.0
                RowCard("${prettyDate(c.date).take(11)} · ${c.cashierName}", "Expected ${c.currency} ${money(c.expectedCash)} · declared ${money(c.declaredCash)}" +
                    (if (v != 0.0) " · variance ${money(c.variance)}" else " · balanced") + (c.verifiedByName?.takeIf { it.isNotBlank() }?.let { "\nVerified by $it" } ?: ""),
                    null, c.statusLabel, if (v != 0.0 && c.status == "SUBMITTED") "URGENT" else c.status, c.localNote)
                if (c.status == "SUBMITTED" && ctx.me.can("cashup.verify") && c.cashierId != ctx.me.id && c.localNote == null) {
                    ActionPanel("Verify cash-up of ${c.cashierName}", listOf(FieldSpec("notes", "Notes")), listOf("ok" to "Verify – cash agrees",
                        "reject" to "Query the variance")) { a, vals ->
                        ctx.sdk.markPending(Entities.CASHUPS, c.id, "Decision queued")
                        ctx.sdk.enqueue("cashup.verify", "Cash-up ${c.cashierName}", Entities.CASHUPS, c.id) {
                            put("cashup", c.id); put("ok", a == "ok"); put("notes", vals["notes"] ?: "")
                        }
                    }
                }
            }
        }
    }
}

// ============================================================ purchase orders
@Composable
fun OrdersScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.PURCHASE_ORDERS, PurchaseOrder.serializer()).collectAsState(initial = emptyList())
    val reqs by ctx.sdk.observe(Entities.REQUISITIONS, Requisition.serializer()).collectAsState(initial = emptyList())
    val ready = reqs.filter { requisitionReady(it) && it.localNote == null }
    AppScreen("Purchase orders", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (ready.isNotEmpty() && ctx.me.can("procurement.order")) {
                item { Text("  Approved requisitions waiting for an order", fontSize = 13.sp, color = CrdcColors.Muted, modifier = Modifier.padding(8.dp)) }
                items(ready, key = { "r" + it.id }) { r ->
                    RowCard(r.purpose.take(60), "${r.number} · ${r.departmentLabel}", "$${money(r.total)}", "Issue order", "APPROVED") { ctx.go(Screen.RequisitionDetail(r.id)) }
                }
            }
            item { Text("  Orders", fontSize = 13.sp, color = CrdcColors.Muted, modifier = Modifier.padding(8.dp)) }
            if (list.isEmpty()) item { Empty("No purchase orders.") }
            items(list, key = { it.id }) { po -> RowCard(po.supplierName, "${po.number} · ${po.requisitionNumber} · ${po.requisitionPurpose.take(40)}",
                "${po.currency} ${money(po.amount)}", po.statusLabel, po.status, po.localNote) { ctx.go(Screen.OrderDetail(po.id)) } }
        }
    }
}

fun requisitionReady(r: Requisition) = r.status == "AUTHORISED" || (r.status == "APPROVED" && !r.needsCeo)

@Composable
fun OrderDetailScreen(ctx: Ctx, id: String) {
    val po by ctx.sdk.observeOne(Entities.PURCHASE_ORDERS, id, PurchaseOrder.serializer()).collectAsState(initial = null)
    AppScreen("Purchase order", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val o = po ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(o.number) {
                KeyValue("Supplier", o.supplierName)
                KeyValue("Requisition", "${o.requisitionNumber} – ${o.requisitionPurpose}")
                KeyValue("Amount", "${o.currency} ${money(o.amount)}")
                KeyValue("Expected delivery", o.expectedDelivery)
                KeyValue("Received", o.deliveredAt?.let { prettyDate(it) })
                KeyValue("Notes", o.notes)
                Row { StatusChip(o.statusLabel, o.status) }
                o.localNote?.let { InfoBox(it) }
            }
            if (o.status == "ISSUED" && ctx.me.can("procurement.order", "voucher.prepare") && o.localNote == null) {
                ActionPanel("Goods / services received", listOf(FieldSpec("notes", "What was delivered (GRV notes)", "multiline")),
                    listOf("receive" to "Confirm received")) { _, v ->
                    ctx.sdk.markPending(Entities.PURCHASE_ORDERS, o.id, "Receipt of goods queued")
                    ctx.sdk.enqueue("po.receive", "Goods received ${o.number}", Entities.PURCHASE_ORDERS, o.id) { put("po", o.id); put("notes", v["notes"] ?: "") }
                }
            }
            if (o.status == "DELIVERED" && ctx.me.can("voucher.prepare")) PrimaryButton("Prepare payment voucher for this order", onClick = { ctx.go(Screen.NewVoucher(o.id)) })
        }
    }
}

/** Issue a purchase order from an approved requisition (procurement officer). */
@Composable
fun IssueOrderPanel(ctx: Ctx, r: Requisition) {
    val suppliers by ctx.sdk.observe(Entities.SUPPLIERS, Supplier.serializer()).collectAsState(initial = emptyList())
    if (!requisitionReady(r) || !ctx.me.can("procurement.order") || r.localNote != null) return
    ActionPanel("Issue purchase order", listOf(
        FieldSpec("supplier", "Supplier", "choice", suppliers.filter { it.status == "ACTIVE" }.map { it.id to it.name }),
        FieldSpec("amount", "Order amount (blank = approved total ${money(r.total)})", "number"),
        FieldSpec("delivery", "Expected delivery (YYYY-MM-DD)"), FieldSpec("notes", "Notes", "multiline"),
    ), listOf("order" to "Issue order")) { _, v ->
        ctx.sdk.markPending(Entities.REQUISITIONS, r.id, "Purchase order queued")
        ctx.sdk.enqueue("po.create", "Order for ${r.number}", Entities.PURCHASE_ORDERS) {
            put("requisition", r.id); put("supplier", v["supplier"] ?: ""); v["amount"]?.takeIf { it.isNotBlank() }?.let { put("amount", it) }
            v["delivery"]?.takeIf { it.isNotBlank() }?.let { put("expected_delivery", it) }; put("notes", v["notes"] ?: "")
        }
    }
}

// ============================================================== correspondence
@Composable
fun CorrespondenceScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.CORRESPONDENCE, Correspondence.serializer()).collectAsState(initial = emptyList())
    AppScreen("Correspondence register", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Record incoming letter", onClick = { ctx.go(Screen.NewCorrespondence) })
        ListScreen {
            item { InfoBox("Letters are answered within 7 working days.") }
            if (list.isEmpty()) item { Empty("No letters.") }
            items(list, key = { it.id }) { c ->
                val late = c.status in listOf("RECEIVED", "ASSIGNED") && zw.gov.chipingerdc.shared.ui.isPast(c.responseDue)
                RowCard(c.subject, "${c.reference} · from ${c.sender} · ${c.departmentLabel}" + (c.assignedToName?.takeIf { it.isNotBlank() }?.let { " · $it" } ?: "") +
                    "\nReply due ${prettyDate(c.responseDue)}" + if (late) " – LATE" else "", null, c.statusLabel, if (late) "URGENT" else c.status, c.localNote) {
                    ctx.go(Screen.CorrespondenceDetail(c.id))
                }
            }
        }
    }
}

@Composable
fun CorrespondenceDetailScreen(ctx: Ctx, id: String) {
    val cc by ctx.sdk.observeOne(Entities.CORRESPONDENCE, id, Correspondence.serializer()).collectAsState(initial = null)
    AppScreen("Letter", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val c = cc ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(c.reference) {
                KeyValue("From", "${c.sender} ${c.senderContact}")
                KeyValue("Subject", c.subject)
                KeyValue("Received", c.dateReceived)
                KeyValue("Department", c.departmentLabel)
                KeyValue("Assigned to", c.assignedToName)
                KeyValue("Reply due", prettyDate(c.responseDue))
                KeyValue("File reference", c.fileReference)
                KeyValue("Response", c.responseSummary)
                Row { StatusChip(c.statusLabel, c.status) }
                c.localNote?.let { InfoBox(it) }
            }
            if (c.localNote == null) ActionPanel("Update", listOf(FieldSpec("status", "Status", "choice", Choices.correspondenceStatuses, c.status),
                FieldSpec("summary", "Response summary", "multiline", initial = c.responseSummary)), listOf("save" to "Save")) { _, v ->
                ctx.sdk.markPending(Entities.CORRESPONDENCE, c.id, "Update queued")
                ctx.sdk.enqueue("correspondence.update", "Letter ${c.reference}", Entities.CORRESPONDENCE, c.id) {
                    put("id", c.id); put("status", v["status"] ?: ""); put("response_summary", v["summary"] ?: "")
                }
            }
        }
    }
}

@Composable
fun NewCorrespondenceScreen(ctx: Ctx) {
    var sender by remember { mutableStateOf("") }
    var contact by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("") }
    var dept by remember { mutableStateOf(ctx.me.department) }
    var fileRef by remember { mutableStateOf("") }
    AppScreen("Record incoming letter", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("From (sender)", sender, { sender = it })
            Field("Sender contact", contact, { contact = it })
            Field("Subject", subject, { subject = it })
            if (ctx.me.can("correspondence.manage")) ChoicePicker("For department", Choices.departments, dept) { dept = it }
            Field("File reference", fileRef, { fileRef = it })
            PrimaryButton("Save – head of department is notified", enabled = sender.isNotBlank() && subject.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("sender", sender); put("subject", subject); put("department", dept)
                    put("department_label", Choices.departments.first { it.first == dept }.second); put("status", "RECEIVED"); put("status_label", "Pending sync")
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved – registered on sync")
                }
                ctx.sdk.enqueue("correspondence.create", "Letter from $sender", Entities.CORRESPONDENCE, id, optimistic) {
                    put("id", id); put("sender", sender); put("sender_contact", contact); put("subject", subject); put("department", dept); put("file_reference", fileRef)
                }
                ctx.back()
            })
        }
    }
}

// ============================================================ staff directory
@Composable
fun StaffScreen(ctx: Ctx) {
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    var q by remember { mutableStateOf("") }
    val shown = staff.filter { it.isActive && (q.isBlank() || it.fullName.contains(q, true) || it.roleLabel.contains(q, true)) }
        .sortedWith(compareBy({ it.department }, { it.fullName }))
    AppScreen("Staff directory", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search name or role", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (shown.isEmpty()) item { Empty("No staff.") }
            items(shown, key = { it.id }) { s ->
                RowCard(s.fullName.ifBlank { s.username }, "${s.roleLabel} · ${Choices.departments.firstOrNull { it.first == s.department }?.second ?: s.department}",
                    s.phone.ifBlank { null })
            }
        }
    }
}

// ================================================ online reports (need a connection)
@Composable
private fun OnlineScreen(ctx: Ctx, title: String, path: String, content: @Composable (JsonObject) -> Unit) {
    var data by remember(path) { mutableStateOf<JsonObject?>(null) }
    var error by remember(path) { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(path, reload) {
        error = null
        runCatching { ctx.sdk.getJson(path) }.onSuccess { data = it }.onFailure { error = it.message ?: "Could not reach the council server." }
    }
    AppScreen(title, onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            error?.let {
                Message("This report is worked out by the council server and needs a connection. $it", MessageKind.WARNING)
                SecondaryButton("Try again", { reload++ })
            }
            data?.let { d -> if (d["detail"] != null) Message(d.str("detail"), MessageKind.ERROR) else content(d) } ?: if (error == null) Text("Loading…") else Unit
        }
    }
}

private fun JsonObject.str(k: String) = this[k]?.jsonPrimitive?.contentOrNull ?: ""
private fun JsonObject.rows(k: String) = (this[k] as? JsonArray)?.map { it.jsonObject } ?: emptyList()

@Composable
private fun AmountTable(title: String, rows: List<JsonObject>) {
    if (rows.isEmpty()) return
    SectionCard(title) {
        rows.forEach { r ->
            val n = r["count"]?.jsonPrimitive?.intOrNull ?: 0
            KeyValue(r.str("label") + if (n > 0) " ($n)" else "", money(r.str("amount")))
        }
    }
}

@Composable
fun FinanceReportScreen(ctx: Ctx) {
    var from by remember { mutableStateOf("") }
    var to by remember { mutableStateOf("") }
    var path by remember { mutableStateOf("reports/finance/") }
    OnlineScreen(ctx, "Financial reports", path) { d ->
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Field("From (YYYY-MM-DD)", from, { from = it }, Modifier.weight(1f))
            Field("To", to, { to = it }, Modifier.weight(1f))
        }
        SecondaryButton("Show period", { path = "reports/finance/?from=$from&to=$to" })
        Text("${d.str("from")} to ${d.str("to")}", fontSize = 13.sp, color = CrdcColors.Muted)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Kpi("Income", "$${money(d.str("income"))}", "${d.str("receipts")} receipts", CrdcColors.Success, Modifier.weight(1f))
            Kpi("Expenditure", "$${money(d.str("expenditure"))}", "${d.str("payments")} payments", CrdcColors.Danger, Modifier.weight(1f))
        }
        Kpi("Net", "$${money(d.str("net"))}", "income less expenditure (USD)", CrdcColors.Blue, Modifier.fillMaxWidth())
        AmountTable("Income by revenue head", d.rows("by_head"))
        AmountTable("Income by channel", d.rows("by_channel"))
        AmountTable("Expenditure by category", d.rows("by_category"))
        AmountTable("Debtors – age of unpaid bills (days)", d.rows("ageing"))
        AmountTable("Bank balances", d.rows("banks"))
    }
}

@Composable
fun ExecutiveScreen(ctx: Ctx) {
    OnlineScreen(ctx, "Executive overview", "reports/executive/") { d ->
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Kpi("Collected today", "$${money(d.str("collected_today"))}", null, CrdcColors.Success, Modifier.weight(1f))
            Kpi("This month", "$${money(d.str("collected_month"))}", "paid out $${money(d.str("paid_out_month"))}", CrdcColors.Green, Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Kpi("Debtors", "$${money(d.str("debtors"))}", "${d.str("overdue_bills")} overdue bills", CrdcColors.Danger, Modifier.weight(1f))
        }
        SectionCard("Service standards – last 90 days") {
            d.rows("charter").forEach { r ->
                val pct = r["pct"]?.jsonPrimitive?.intOrNull
                KeyValue(r.str("label"), (pct?.let { "$it%" } ?: "—") + " of ${r.str("count")}")
            }
        }
        SectionCard("Departments") {
            d.rows("departments").forEach { r ->
                Column(Modifier.fillMaxWidth().bottomRule().padding(vertical = 6.dp)) {
                    Text(r.str("label"), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = CrdcColors.Blue)
                    Text("Tasks ${r.str("tasks_open")} open (${r.str("tasks_overdue")} overdue) · complaints ${r.str("complaints_open")} · faults ${r.str("requests_open")}" +
                        " · audit findings ${r.str("findings_open")} · requests for funds ${r.str("funds_waiting")}", fontSize = 12.sp, color = CrdcColors.Muted)
                }
            }
        }
        SecondaryButton("Open any department", { ctx.go(Screen.Department()) })
    }
}

@Composable
fun AuditTrailScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    var path by remember { mutableStateOf("audit/") }
    OnlineScreen(ctx, "Audit trail", path) { d ->
        Field("Search user, record or message", q, { q = it })
        SecondaryButton("Search", { path = "audit/?q=${q.trim().replace(" ", "+")}" })
        InfoBox("Every change, approval, payment, login and export – tamper-evident (hash-chained). Read-only.")
        d.rows("items").forEach { r ->
            Column(Modifier.fillMaxWidth().background(androidx.compose.ui.graphics.Color.White).bottomRule().padding(vertical = 6.dp)) {
                Text("${r.str("action")} · ${r.str("object").ifBlank { r.str("model") }}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text("${r.str("user")} · ${prettyDate(r.str("when"))} · ${r.str("channel")}", fontSize = 11.sp, color = CrdcColors.Muted)
                if (r.str("message").isNotBlank()) Text(r.str("message"), fontSize = 12.sp)
            }
        }
    }
}
