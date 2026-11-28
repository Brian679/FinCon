package zw.gov.chipingerdc.council

import kotlinx.coroutines.launch

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.FundsRequest
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.model.Memo
import zw.gov.chipingerdc.shared.model.RouteStep
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.Caption
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
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

const val FUNDS_ROUTE = "You → Head of Department → Administration Officer → Accountant → Treasurer → CEO → (purchases: invoice attached, " +
    "purchase confirmed) → payment voucher (Accountant checks, Treasurer approves the payment, CEO if large) → paid. You are notified at every step."

val PURCHASE_TYPES = listOf("PURCHASE", "FUEL", "REPAIRS", "TRAINING")

/** Can this officer decide the request now? (the server lists who may). */
fun fundsStage(me: Me, r: FundsRequest): String? =
    if (r.localNote == null && me.id in r.deciders && r.requestedBy != me.id) r.statusLabel.removePrefix("Waiting for ") else null

private fun canPreparePayment(me: Me, r: FundsRequest) = r.status == "P_PAY" && me.can("voucher.prepare") && r.localNote == null

fun fundsApprovals(me: Me, list: List<FundsRequest>): List<Approval> = buildList {
    list.forEach { r ->
        fundsStage(me, r)?.let { add(Approval("Request for funds", r.reference, "${r.departmentLabel} · ${r.title} · ${r.currency} ${money(r.total)}", it, Screen.FundsDetail(r.id))) }
        if (canPreparePayment(me, r)) add(Approval("Request for funds", r.reference, "${r.title} · ${r.currency} ${money(r.total)}", "Prepare payment voucher", Screen.FundsDetail(r.id)))
        if (r.status == "P_CONF" && r.localNote == null && (r.requestedBy == me.id || me.can("procurement.order")))
            add(Approval("Request for funds", r.reference, "${r.title} · ${r.currency} ${money(r.total)}", "Attach invoice & confirm purchase", Screen.FundsDetail(r.id)))
    }
}

// ------------------------------------------------------------------ list
@Composable
fun FundsScreen(ctx: Ctx) {
    val me = ctx.me
    val all by ctx.sdk.observe(Entities.FUNDS_REQUESTS, FundsRequest.serializer()).collectAsState(initial = emptyList())
    val waiting = all.filter { fundsStage(me, it) != null || canPreparePayment(me, it) }
    val tabs = buildList {
        add("mine" to "Mine")
        if (me.isHead || me.can("funds.admin_approve", "funds.treasurer_approve", "funds.ceo_approve", "voucher.prepare")) add("waiting" to "For me (${waiting.size})")
        if (me.isHead) add("dept" to "Department")
        if (me.can("funds.view_all", "funds.admin_approve")) add("all" to "All")
    }
    var tab by remember { mutableStateOf(if (waiting.isNotEmpty()) "waiting" else "mine") }
    val shown = when (tab) {
        "waiting" -> waiting
        "dept" -> all.filter { it.department == me.department }
        "all" -> all
        else -> all.filter { it.requestedBy == me.id }
    }
    AppScreen("Requests for funds", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        zw.gov.chipingerdc.shared.ui.TopAction { PrimaryButton("+ New request (T&S, advance, purchase …)", onClick = { ctx.go(Screen.NewFunds) }) }
        Tabs(tabs, tab) { tab = it }
        ListScreen {
            if (shown.isEmpty()) item { Empty("No requests here.") }
            items(shown, key = { it.id }) { r ->
                val where = if (r.isOpen || r.status == "RETURNED") "Now: ${r.whereNow}" + if (r.daysWaiting > 0) " · ${r.daysWaiting} day(s)" else "" else r.departmentLabel
                RowCard(r.title, "${r.reference} · ${r.requestedByName} · $where", "${r.currency} ${money(r.total)}", r.statusLabel, r.status, r.localNote) {
                    ctx.go(Screen.FundsDetail(r.id))
                }
            }
        }
    }
}

@Composable
fun Tabs(tabs: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().background(CrdcColors.Darkened).bottomRule(CrdcColors.Border), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        tabs.forEach { (key, label) ->
            val on = key == selected
            Text(label, fontSize = 13.sp, color = if (on) CrdcColors.Body else CrdcColors.Blue, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                modifier = Modifier.background(if (on) Color.White else CrdcColors.Darkened).clickable { onSelect(key) }
                    .padding(horizontal = 12.dp, vertical = 10.dp))
        }
    }
}

// ---------------------------------------------------------------- detail
@Composable
fun RouteTracker(steps: List<RouteStep>) {
    Column(Modifier.fillMaxWidth()) {
        steps.forEachIndexed { i, s ->
            val (mark, color) = when (s.state) {
                "done" -> "✔" to CrdcColors.Success
                "current" -> "●" to CrdcColors.Warning
                "skipped" -> "–" to CrdcColors.Muted
                "rejected", "returned" -> "✖" to CrdcColors.Danger
                else -> "○" to CrdcColors.Border
            }
            Row(Modifier.fillMaxWidth().background(if (s.state == "current") Color(0xFFFFF8E1) else Color.White).bottomRule().padding(8.dp),
                verticalAlignment = Alignment.Top) {
                Text(mark, color = color, fontSize = 16.sp, fontWeight = FontWeight.Bold, modifier = Modifier.width(24.dp))
                Column(Modifier.weight(1f)) {
                    Text("${i + 1}. ${s.label}", fontSize = 14.sp, color = CrdcColors.Body,
                        fontWeight = if (s.state == "current") FontWeight.SemiBold else FontWeight.Normal)
                    val sub = listOf(s.who, if (s.`when`.isNotBlank()) prettyDate(s.`when`) else "").filter { it.isNotBlank() }.joinToString(" · ")
                    if (sub.isNotBlank()) Text(sub, fontSize = 12.sp, color = CrdcColors.Muted)
                    if (s.note.isNotBlank()) Text(s.note, fontSize = 12.sp, color = if (s.state == "current") CrdcColors.Warning else CrdcColors.Muted)
                }
                Text(when (s.state) { "done" -> "Done"; "current" -> "With them now"; "skipped" -> "Not needed"; "rejected" -> "Rejected"
                    "returned" -> "Returned"; else -> "Waiting" }, fontSize = 11.sp, color = color)
            }
        }
    }
}

@Composable
fun FundsDetailScreen(ctx: Ctx, id: String) {
    val me = ctx.me
    val rr by ctx.sdk.observeOne(Entities.FUNDS_REQUESTS, id, FundsRequest.serializer()).collectAsState(initial = null)
    AppScreen("Request for funds", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val r = rr ?: return@AppScreen Empty("Not found")
        fun act(action: String, comment: String = "", note: String) {
            ctx.sdk.markPending(Entities.FUNDS_REQUESTS, r.id, note)
            ctx.sdk.enqueue("funds.action", "${r.reference}: $action", Entities.FUNDS_REQUESTS, r.id) {
                put("id", r.id); put("action", action); put("comment", comment)
            }
        }
        ScrollColumn {
            SectionCard(r.reference) {
                Text(r.title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Row { StatusChip(r.statusLabel, r.status) }
                if (r.localNote != null) InfoBox(r.localNote!!)
                if (r.isOpen) Message("Currently with: ${r.whereNow}" + if (r.daysWaiting > 0) " – waiting ${r.daysWaiting} day(s)" else "", MessageKind.WARNING)
                if (r.decisionNote.isNotBlank()) Message(r.decisionNote, if (r.status == "RETURNED") MessageKind.WARNING else MessageKind.ERROR)
            }
            if (r.payeeDiffers) Message("Payment goes to ${r.payeeName}, not to the requester. Check the supporting documents before approving.", MessageKind.ERROR)
            SectionCard("Where is it now?") { RouteTracker(r.route) }
            SectionCard("Details") {
                KeyValue("Type", r.requestTypeLabel)
                KeyValue("Department", r.departmentLabel)
                KeyValue("Requested by", r.requestedByName)
                KeyValue("Purpose", r.purpose)
                if (r.destination.isNotBlank()) KeyValue("Destination", r.destination)
                if (r.departDate != null) KeyValue("Travel dates", "${r.departDate} – ${r.returnDate ?: ""}")
                if (r.travellers.isNotBlank()) KeyValue("Officers travelling", r.travellers)
                r.neededBy?.let { KeyValue("Needed by", it) }
                KeyValue("Pay to", r.payeeName.ifBlank { r.requestedByName } + " · " + r.paymentMethodLabel)
                if (r.paymentDetails.isNotBlank()) KeyValue("Bank / mobile money", r.paymentDetails)
                r.voucherNumber?.takeIf { it.isNotBlank() }?.let { KeyValue("Payment voucher", "$it – ${r.voucherStatus}") }
            }
            SectionCard("What is requested") {
                r.lines.forEach { KeyValue("${it.quantity.removeSuffix(".00")} × ${it.description} @ ${money(it.unitCost)}", money(it.total)) }
                KeyValue("Total", "${r.currency} ${money(r.total)}")
            }
            val mineReq = r.requestedBy == me.id
            FilesCard(ctx.sdk, "funds", r.id, r.attachments,
                r.localNote == null && r.status !in listOf("PAID", "COMPLETED", "REJECTED", "CANCELLED") &&
                    (mineReq || me.can("procurement.order", "voucher.prepare", "funds.accountant_approve")),
                when { r.status == "P_CONF" -> "INVOICE"; r.status in listOf("DRAFT", "RETURNED") && r.requestType in PURCHASE_TYPES -> "QUOTE"; else -> "EVIDENCE" },
                "Quotations, invoices & evidence")
            if (r.status == "P_CONF" && r.localNote == null && (mineReq || me.can("procurement.order"))) {
                val hasInvoice = r.attachments.any { it.kind in listOf("INVOICE", "DELIVERY") }
                if (!hasInvoice) Message("Attach the invoice or delivery note, then confirm the purchase.", MessageKind.WARNING)
                ActionPanel("Confirm the purchase", listOf(FieldSpec("comment", "Note (e.g. 400 litres delivered to the depot)")),
                    listOf("confirm" to "Confirm purchase")) { _, v -> act("confirm", v["comment"] ?: "", "Confirmation queued") }
            }
            fundsStage(me, r)?.let { stage ->
                ActionPanel("Your decision – $stage", listOf(FieldSpec("comment", "Comment (required to return or reject)", "multiline")),
                    listOf("approve" to "Approve – send to next stage", "return" to "Return for changes", "reject" to "Reject"),
                    note = "Queued if you are offline. You cannot approve your own request or approve twice.") { a, v ->
                    act(a, v["comment"] ?: "", "Decision queued: $a")
                }
            }
            if (canPreparePayment(me, r)) {
                ActionPanel("Finance – prepare payment", listOf(FieldSpec("method", "Payment method", "choice", Choices.fundsPayment, r.paymentMethod)),
                    listOf("pay" to "Prepare payment voucher"), note = "The voucher then needs checking and the Treasurer's payment approval.") { _, v ->
                    ctx.sdk.markPending(Entities.FUNDS_REQUESTS, r.id, "Payment voucher queued")
                    ctx.sdk.enqueue("funds.action", "${r.reference}: prepare payment", Entities.FUNDS_REQUESTS, r.id) {
                        put("id", r.id); put("action", "pay"); put("method", v["method"] ?: r.paymentMethod)
                    }
                }
            }
            val mine = r.requestedBy == me.id
            if (r.isOpen && me.id !in r.deciders && (mine || (me.isHead && me.department == r.department))) {
                ActionPanel("Follow up", listOf(FieldSpec("comment", "Message (optional)")), listOf("remind" to "Send reminder"),
                    note = "Reminds: ${r.whereNow}." + (r.lastReminderAt?.let { " Last reminder ${prettyDate(it)}." } ?: "")) { _, v ->
                    act("remind", v["comment"] ?: "", "Reminder queued")
                }
            }
            if (mine && r.status in listOf("RETURNED", "DRAFT")) PrimaryButton(if (r.status == "DRAFT") "Submit for approval" else "Resubmit for approval",
                enabled = r.requestType !in PURCHASE_TYPES || r.attachments.isNotEmpty(), onClick = { act("submit", note = "Submission queued") })
            if (mine && r.status in listOf("P_HOD", "P_ADMIN", "P_ACC", "P_TREAS", "P_CEO", "RETURNED")) SecondaryButton("Cancel request", { act("cancel", note = "Cancellation queued") })
            if (r.history.isNotEmpty()) SectionCard("History") {
                r.history.forEach { h ->
                    Column(Modifier.fillMaxWidth().bottomRule().padding(vertical = 6.dp)) {
                        Text("${h.stage} – ${h.decision.lowercase().replaceFirstChar { it.uppercase() }}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text("${h.user} · ${prettyDate(h.`when`)}", fontSize = 12.sp, color = CrdcColors.Muted)
                        if (h.comment.isNotBlank()) Text(h.comment, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ form
private class LineRow(description: String = "", quantity: String = "1", unitCost: String = "") {
    var description by mutableStateOf(description)
    var quantity by mutableStateOf(quantity)
    var unitCost by mutableStateOf(unitCost)
}

@Composable
fun NewFundsScreen(ctx: Ctx) {
    var type by remember { mutableStateOf("TRAVEL") }
    var title by remember { mutableStateOf("") }
    var purpose by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("") }
    var depart by remember { mutableStateOf("") }
    var ret by remember { mutableStateOf("") }
    var travellers by remember { mutableStateOf(ctx.me.fullName) }
    var neededBy by remember { mutableStateOf("") }
    var payment by remember { mutableStateOf(true) }
    var method by remember { mutableStateOf("MOBILE") }
    var details by remember { mutableStateOf("") }
    var payee by remember { mutableStateOf("") }
    val rows = remember { mutableStateListOf(LineRow("Subsistence allowance", "1", ""), LineRow("Accommodation", "1", "")) }
    val files = remember { mutableStateListOf<zw.gov.chipingerdc.shared.PickedFile>() }
    val total = rows.sumOf { (it.quantity.toDoubleOrNull() ?: 0.0) * (it.unitCost.toDoubleOrNull() ?: 0.0) }
    AppScreen("New request", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            InfoBox("Department: ${ctx.me.departmentLabel}. $FUNDS_ROUTE")
            ChoicePicker("Type of request", Choices.fundsTypes, type) { type = it }
            Field("What is it for?", title, { title = it })
            Field("Purpose / justification", purpose, { purpose = it }, singleLine = false, minLines = 2)
            if (type == "TRAVEL" || type == "TRAINING") SectionCard("Travel details") {
                Field("Destination", destination, { destination = it })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field("Departure (YYYY-MM-DD)", depart, { depart = it }, Modifier.weight(1f))
                    Field("Return", ret, { ret = it }, Modifier.weight(1f))
                }
                Field("Officers travelling", travellers, { travellers = it })
            }
            Field("Needed by (YYYY-MM-DD)", neededBy, { neededBy = it })
            rows.forEachIndexed { i, row ->
                SectionCard("Line ${i + 1}") {
                    Field("Description", row.description, { row.description = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Field("Qty / days", row.quantity, { row.quantity = it }, Modifier.weight(1f), number = true)
                        Field("Rate (USD)", row.unitCost, { row.unitCost = it }, Modifier.weight(1f), number = true)
                    }
                    if (rows.size > 1) SecondaryButton("Remove line", { rows.removeAt(i) })
                }
            }
            SecondaryButton("+ Add line", { rows.add(LineRow()) })
            Text("Total: USD ${money(total.toString())}", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(payment, { payment = it })
                Text("Money must be paid out", fontSize = 14.sp)
            }
            if (payment) {
                ChoicePicker("Payment method", Choices.fundsPayment, method) { method = it }
                Field("Bank / mobile money details", details, { details = it })
                Field("Pay to (blank = me)", payee, { payee = it })
            }
            val needsQuote = type in PURCHASE_TYPES
            PendingFiles(files, if (needsQuote) "Quotation / supporting documents (required)" else "Supporting documents")
            val valid = title.isNotBlank() && purpose.isNotBlank() && rows.all { it.description.isNotBlank() && (it.unitCost.toDoubleOrNull() ?: 0.0) > 0 } &&
                (type != "TRAVEL" || (destination.isNotBlank() && depart.isNotBlank())) && (!needsQuote || files.isNotEmpty())
            PrimaryButton("Submit for approval", enabled = valid, onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("title", title); put("purpose", purpose); put("department", ctx.me.department)
                    put("department_label", ctx.me.departmentLabel); put("requested_by", ctx.me.id); put("requested_by_name", ctx.me.fullName)
                    put("request_type", type); put("request_type_label", Choices.fundsTypes.first { it.first == type }.second)
                    put("total", total.toString()); put("currency", "USD"); put("status", "P_HOD"); put("status_label", "Pending sync")
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved on phone – goes to your Head of Department when you are online")
                }
                ctx.sdk.enqueue("funds.create", "Request: $title", Entities.FUNDS_REQUESTS, id, optimistic) {
                    put("id", id); put("request_type", type); put("title", title); put("purpose", purpose); put("destination", destination)
                    if (depart.isNotBlank()) put("depart_date", depart)
                    if (ret.isNotBlank()) put("return_date", ret)
                    put("travellers", travellers); if (neededBy.isNotBlank()) put("needed_by", neededBy)
                    put("requires_payment", payment); put("payment_method", method); put("payment_details", details); put("payee_name", payee)
                    val toSend = files.toList()
                    put("submit", toSend.isEmpty())
                    putJsonArray("lines") {
                        rows.forEach { r -> addJsonObject { put("description", r.description); put("quantity", r.quantity); put("unit_cost", r.unitCost) } }
                    }
                }
                val toSend = files.toList()
                if (toSend.isNotEmpty()) ctx.sdk.scope.launch {
                    runCatching {
                        ctx.sdk.sync.sync()
                        toSend.forEach { uploadAttachment(ctx.sdk, "funds", id, if (needsQuote) "QUOTE" else "EVIDENCE", it) }
                        ctx.sdk.enqueue("funds.action", "Submit: $title", Entities.FUNDS_REQUESTS, id) { put("id", id); put("action", "submit"); put("comment", "") }
                    }
                }
                ctx.back()
            })
        }
    }
}

// ================================================================= memos
@Composable
fun MemosScreen(ctx: Ctx) {
    val me = ctx.me
    val all by ctx.sdk.observe(Entities.MEMOS, Memo.serializer()).collectAsState(initial = emptyList())
    var tab by remember { mutableStateOf("in") }
    val received = all.filter { it.sender != me.id }
    val shown = if (tab == "in") received else all.filter { it.sender == me.id }
    AppScreen("Memos", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        zw.gov.chipingerdc.shared.ui.TopAction { PrimaryButton("+ Send memo / request to a department", onClick = { ctx.go(Screen.NewMemo) }) }
        Tabs(listOf("in" to "Received (${received.count { it.status == "SENT" }} new)", "out" to "Sent"), tab) { tab = it }
        ListScreen {
            if (shown.isEmpty()) item { Empty("No memos.") }
            items(shown, key = { it.id }) { m ->
                val who = if (tab == "in") "From ${m.senderName} (${m.fromDepartmentLabel})" else "To ${m.toUserName?.takeIf { it.isNotBlank() } ?: "Head of"} ${m.toDepartmentLabel}"
                RowCard(m.subject, "${m.reference} · ${m.kindLabel} · $who", null, m.statusLabel, m.status, m.localNote) { ctx.go(Screen.MemoDetail(m.id)) }
            }
        }
    }
}

@Composable
fun MemoDetailScreen(ctx: Ctx, id: String) {
    val me = ctx.me
    val mm by ctx.sdk.observeOne(Entities.MEMOS, id, Memo.serializer()).collectAsState(initial = null)
    val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
    AppScreen("Memo", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val m = mm ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${m.reference} – ${m.kindLabel}") {
                Text(m.subject, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Row { StatusChip(m.statusLabel, m.status) }
                KeyValue("From", "${m.senderName} (${m.fromDepartmentLabel})")
                KeyValue("To", "${m.toUserName?.takeIf { it.isNotBlank() } ?: "Head of"} ${m.toDepartmentLabel}")
                KeyValue("Priority", m.priorityLabel)
                KeyValue("Sent", prettyDate(m.createdAt))
                m.taskReference?.takeIf { it.isNotBlank() }?.let { KeyValue("Task", "$it – ${m.taskAssignee} · ${m.taskStatus}") }
                Text(m.body, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
                if (m.localNote != null) InfoBox(m.localNote!!)
            }
            if (m.replies.isNotEmpty()) SectionCard("Replies") {
                m.replies.forEach { r ->
                    Column(Modifier.fillMaxWidth().bottomRule().padding(vertical = 6.dp)) {
                        Text("${r.author} (${r.department})", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text(prettyDate(r.`when`), fontSize = 11.sp, color = CrdcColors.Muted)
                        Text(r.body, fontSize = 13.sp)
                    }
                }
            }
            if (m.status != "CLOSED") ActionPanel("Reply", listOf(FieldSpec("body", "Reply", "multiline")), listOf("reply" to "Send reply", "close" to "Reply & close")) { a, v ->
                ctx.sdk.markPending(Entities.MEMOS, m.id, "Reply queued")
                ctx.sdk.enqueue("memo.reply", "${m.reference}: reply", Entities.MEMOS, m.id) {
                    put("id", m.id); put("body", v["body"] ?: ""); put("close", a == "close")
                }
            }
            val officers = staff.filter { it.department == m.toDepartment && it.isActive && it.userId != me.id }
            if (me.isHead && me.department == m.toDepartment && m.taskReference.isNullOrBlank() && officers.isNotEmpty()) {
                ActionPanel("Assign as a task to my officer", listOf(FieldSpec("who", "Officer", "choice", officers.map { it.userId.toString() to "${it.fullName} – ${it.roleLabel}" }),
                    FieldSpec("due", "Due date (YYYY-MM-DD)")), listOf("task" to "Create task")) { _, v ->
                    ctx.sdk.markPending(Entities.MEMOS, m.id, "Task queued")
                    ctx.sdk.enqueue("memo.reply", "${m.reference}: assign", Entities.MEMOS, m.id) {
                        put("id", m.id); put("assigned_to", v["who"]?.toLongOrNull() ?: 0L); v["due"]?.takeIf { it.isNotBlank() }?.let { put("due_date", it) }
                    }
                }
            }
        }
    }
}

@Composable
fun NewMemoScreen(ctx: Ctx) {
    var kind by remember { mutableStateOf("ACTION") }
    var dept by remember { mutableStateOf(Choices.departments.first { it.first != ctx.me.department }.first) }
    var priority by remember { mutableStateOf("NORMAL") }
    var subject by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    AppScreen("New memo", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            InfoBox("Goes to the Head of the department you choose. They can reply or give it to one of their officers as a task.")
            ChoicePicker("Type", Choices.memoKinds, kind) { kind = it }
            ChoicePicker("To department", Choices.departments, dept) { dept = it }
            ChoicePicker("Priority", Choices.priorities, priority) { priority = it }
            Field("Subject", subject, { subject = it })
            Field("Message", body, { body = it }, singleLine = false, minLines = 4)
            PrimaryButton("Send", enabled = subject.isNotBlank() && body.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val label = Choices.departments.first { it.first == dept }.second
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("kind", kind); put("kind_label", Choices.memoKinds.first { it.first == kind }.second)
                    put("sender", ctx.me.id); put("sender_name", ctx.me.fullName); put("from_department_label", ctx.me.departmentLabel)
                    put("to_department", dept); put("to_department_label", label); put("subject", subject); put("body", body)
                    put("status", "SENT"); put("status_label", "Pending sync"); put("updated_at", ctx.sdk.nowIso()); put("local_note", "Will be sent when you are online")
                }
                ctx.sdk.enqueue("memo.create", "Memo to $label: $subject", Entities.MEMOS, id, optimistic) {
                    put("id", id); put("kind", kind); put("to_department", dept); put("priority", priority); put("subject", subject); put("body", body)
                }
                ctx.back()
            })
        }
    }
}
