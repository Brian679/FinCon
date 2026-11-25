package zw.gov.chipingerdc.client

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.AppNotification
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.OnlinePayment
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.RegisterRequest
import zw.gov.chipingerdc.shared.model.RevenueHead
import zw.gov.chipingerdc.shared.model.ServiceRequest
import zw.gov.chipingerdc.shared.model.ServiceStandard
import zw.gov.chipingerdc.shared.model.StandApplication
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
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private const val ONLINE_ONLY = "This needs an internet connection. Please connect and try again."

// ------------------------------------------------------------------ register
@Composable
fun RegisterScreen(sdk: CouncilSdk, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var first by remember { mutableStateOf("") }
    var last by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var nid by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var p1 by remember { mutableStateOf("") }
    var p2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    AppScreen("Create account", onBack = onDone) {
        ScrollColumn {
            Text("For residents, ratepayers and businesses in Chipinge District.", color = CrdcColors.Muted)
            Field("First name", first, { first = it })
            Field("Surname", last, { last = it })
            Field("Username", username, { username = it })
            Field("Email", email, { email = it })
            Field("Mobile number", phone, { phone = it })
            Field("National ID", nid, { nid = it })
            Field("Ward (optional)", ward, { ward = it }, number = true)
            Field("Password (min. 8 characters)", p1, { p1 = it }, password = true)
            Field("Confirm password", p2, { p2 = it }, password = true)
            msg?.let { InfoBox(it.first, if (it.second) CrdcColors.Success else CrdcColors.Danger) }
            PrimaryButton("Create account", busy = busy, enabled = listOf(first, last, username, phone, nid, p1).all { it.isNotBlank() } && p1 == p2, onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        sdk.register(sdk.session.baseUrl, RegisterRequest(first, last, username, email, phone, nid, ward, p1, p2))
                        sdk.login(sdk.session.baseUrl, username, p1)
                    }.onFailure { msg = (it.message ?: ONLINE_ONLY) to false }
                    busy = false
                }
            })
        }
    }
}

// ---------------------------------------------------------------------- home
@Composable
fun ClientHome(ctx: CCtx) {
    val sdk = ctx.sdk
    val accounts by sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val notes by sdk.observe(Entities.NOTIFICATIONS, AppNotification.serializer()).collectAsState(initial = emptyList())
    val unpaid = bills.filter { it.status in listOf("UNPAID", "PART") }
    val total = accounts.sumOf { it.balance.toDoubleOrNull() ?: 0.0 }
    AppScreen("Chipinge RDC", sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow, actions = {
        TextButton(onClick = { sdk.logout() }) { Text("Log out", color = Color.White) }
    }) {
        ScrollColumn {
            Text("Hello, ${ctx.me.fullName.ifBlank { ctx.me.username }}", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            if (accounts.isEmpty()) {
                InfoBox("Register your stand or shop, or link your council account using the account number on your bill.")
                PrimaryButton("Register my stand / shop", onClick = { ctx.go(CScreen.RegisterStand) })
                PrimaryButton("Link with account number", color = CrdcColors.Blue, onClick = { ctx.go(CScreen.LinkAccount) })
            } else {
                Kpi("Total amount due", "$${money(total.toString())}", "${unpaid.size} unpaid bill(s)", if (total > 0) CrdcColors.Danger else CrdcColors.Green, Modifier.fillMaxWidth())
                PrimaryButton("Pay now (EcoCash / OneMoney / InnBucks)", onClick = { ctx.go(CScreen.Pay(null, null)) })
                accounts.forEach { a ->
                    RowCard(a.name, a.accountNumber, "$${money(a.balance)}", a.statusLabel, a.status) { ctx.go(CScreen.Account(a.id)) }
                }
            }
            val tiles = listOf(
                "My stands & shops" to CScreen.MyStands, "Building plans" to CScreen.Plans,
                "Payment history" to CScreen.Receipts, "Licences" to CScreen.Licences, "Report a problem" to CScreen.Problems,
                "Complaints & feedback" to CScreen.Feedback, "Stand applications" to CScreen.Stands,
                "Notifications (${notes.count { !it.isRead }})" to CScreen.Notifications, "Link another account" to CScreen.LinkAccount,
                "Client Charter" to CScreen.Charter, "Sync status" to CScreen.SyncCentre,
            )
            tiles.chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { (label, screen) -> Kpi(label, "›", null, CrdcColors.Blue, Modifier.weight(1f)) { ctx.go(screen) } }
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

// ------------------------------------------------------------ link account
@Composable
fun LinkAccountScreen(ctx: CCtx) {
    val scope = rememberCoroutineScope()
    var number by remember { mutableStateOf("") }
    var verifier by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Link council account", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            InfoBox("Enter the account number on your bill and the phone number or National ID registered on that account.")
            Field("Account number (e.g. CR2026-00001)", number, { number = it })
            Field("Phone number or National ID", verifier, { verifier = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Link account", busy = busy, enabled = number.isNotBlank() && verifier.isNotBlank(), onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        val acc = ctx.sdk.postJson("client/link-account/", buildJsonObject { put("account_number", number); put("verifier", verifier) })
                        ctx.sdk.store.upsert(Entities.ACCOUNTS, acc)
                        // Fetch the full history of the newly linked account.
                        listOf(Entities.ACCOUNTS, Entities.PROPERTIES, Entities.BILLS, Entities.RECEIPTS, Entities.LICENCES).forEach { ctx.sdk.store.resetCursor(it) }
                        ctx.sdk.sync.sync()
                        ctx.back()
                    }.onFailure { error = it.message ?: ONLINE_ONLY }
                    busy = false
                }
            })
        }
    }
}

@Composable
fun AccountScreen(ctx: CCtx, id: String) {
    val sdk = ctx.sdk
    val a by sdk.observeOne(Entities.ACCOUNTS, id, ClientAccount.serializer()).collectAsState(initial = null)
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    AppScreen("My account", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val acc = a ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(acc.name) {
                KeyValue("Account no.", acc.accountNumber)
                KeyValue("Amount due", "USD ${money(acc.balance)}")
                props.filter { it.account == acc.id }.forEach { KeyValue("Stand ${it.standNumber}", "${it.location} · $${money(it.monthlyRates)}/month") }
            }
            PrimaryButton("Pay", onClick = { ctx.go(CScreen.Pay(acc.id, null)) })
            SectionCard("Bills") {
                val mine = bills.filter { it.account == acc.id }
                if (mine.isEmpty()) Text("No bills.", color = CrdcColors.Muted)
                mine.forEach { b ->
                    RowCard(b.description, "${b.number} · due ${prettyDate(b.dueDate)}", "$${money(b.outstanding)}", b.statusLabel, b.status,
                        onClick = if (b.status in listOf("UNPAID", "PART")) ({ ctx.go(CScreen.Pay(acc.id, b.id)) }) else null)
                }
            }
        }
    }
}

// ----------------------------------------------------------------- payments
@Composable
fun PayScreen(ctx: CCtx, accountId: String?, billId: String?) {
    val sdk = ctx.sdk
    val scope = rememberCoroutineScope()
    val accounts by sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val heads by sdk.observe(Entities.REVENUE_HEADS, RevenueHead.serializer()).collectAsState(initial = emptyList())
    val bill = remember { billId?.let { sdk.store.get(Entities.BILLS, it, Bill.serializer()) } }
    var account by remember { mutableStateOf<ClientAccount?>(null) }
    if (account == null && accounts.isNotEmpty()) account = accounts.firstOrNull { it.id == (accountId ?: bill?.account) } ?: accounts.first()
    var head by remember { mutableStateOf<RevenueHead?>(null) }
    if (head == null && heads.isNotEmpty()) head = heads.firstOrNull { it.id == bill?.revenueHead } ?: heads.firstOrNull { it.code == "RATES" } ?: heads.first()
    var amount by remember { mutableStateOf(bill?.outstanding ?: "") }
    var method by remember { mutableStateOf("ECOCASH") }
    var phone by remember { mutableStateOf(ctx.me.phone) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Pay online", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (bill != null) InfoBox("Paying bill ${bill.number}: ${bill.description}")
            Picker("Account", accounts, account, { "${it.accountNumber} – ${it.name} (owes $${money(it.balance)})" }, { account = it })
            if (bill == null) Picker("Paying for", heads, head, { it.name }, { head = it })
            Field("Amount (USD)", amount, { amount = it }, number = true)
            ChoicePicker("Pay with", Choices.mobileMoney, method) { method = it }
            Field("Mobile money number", phone, { phone = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Send payment prompt to my phone", busy = busy, enabled = account != null && (amount.toDoubleOrNull() ?: 0.0) >= 1 && phone.isNotBlank(), onClick = {
                busy = true
                error = null
                scope.launch {
                    runCatching {
                        val p = sdk.postJson("payments/", buildJsonObject {
                            put("account", account!!.id); put("amount", amount); put("method", method); put("phone", phone)
                            bill?.let { put("bill", it.id) } ?: head?.let { put("revenue_head", it.id) }
                        })
                        sdk.store.upsert(Entities.ONLINE_PAYMENTS, p)
                        val ref = AppJson.decodeFromJsonElement(OnlinePayment.serializer(), p).reference
                        ctx.back()
                        ctx.go(CScreen.Payment(ref))
                    }.onFailure { error = it.message ?: ONLINE_ONLY }
                    busy = false
                }
            })
            Text("Your official receipt is issued immediately when the payment is confirmed (Client Charter: payment confirmation – immediate).",
                fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

@Composable
fun PaymentScreen(ctx: CCtx, reference: String) {
    val sdk = ctx.sdk
    val scope = rememberCoroutineScope()
    var payment by remember { mutableStateOf<OnlinePayment?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    suspend fun call(action: String?) {
        runCatching {
            val obj: JsonObject = if (action == null) sdk.getJson("payments/$reference/")
            else sdk.postJson("payments/$reference/", buildJsonObject { put("action", action) })
            sdk.store.upsert(Entities.ONLINE_PAYMENTS, obj)
            payment = AppJson.decodeFromJsonElement(OnlinePayment.serializer(), obj)
            if (payment?.status == "PAID") sdk.sync.sync()
            error = null
        }.onFailure { error = it.message ?: ONLINE_ONLY }
    }
    LaunchedEffect(reference) {
        while (true) {
            call(null)
            if (payment?.status != "PENDING") break
            delay(5_000)
        }
    }
    AppScreen("Payment $reference", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            val p = payment
            if (p == null) Text("Contacting the council…")
            else SectionCard("${p.currency} ${money(p.amount)}") {
                Row { StatusChip(p.statusLabel, p.status) }
                when (p.status) {
                    "PENDING" -> {
                        Text("Check your phone (${p.phone}) and enter your PIN to approve the payment.")
                        if (p.provider == "simulated") {
                            InfoBox("Test mode – no real money moves. Press Confirm to simulate approving the prompt.", CrdcColors.Warning)
                            PrimaryButton("Confirm (test mode)", onClick = { scope.launch { call("confirm") } })
                        } else PrimaryButton("I have approved – check status", onClick = { scope.launch { call("check") } })
                        SecondaryButton("Cancel payment", { scope.launch { call("cancel") } })
                    }
                    "PAID" -> {
                        InfoBox("Payment received. Receipt ${p.receiptNumber} issued.", CrdcColors.Success)
                        PrimaryButton("View receipt", onClick = { p.receipt?.let { ctx.go(CScreen.Receipt(it)) } })
                    }
                    else -> InfoBox("This payment was ${p.statusLabel.lowercase()}.", CrdcColors.Danger)
                }
            }
            error?.let { InfoBox(it, CrdcColors.Danger) }
        }
    }
}

@Composable
fun ReceiptsScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    AppScreen("Payment history", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No payments yet.") }
            items(list.filter { it.status != "VOIDED" }, key = { it.id }) { r ->
                RowCard(r.revenueHeadName, "${r.number} · ${prettyDate(r.createdAt)} · ${r.accountNumber ?: ""}", "${r.currency} ${money(r.amount)}") {
                    ctx.go(CScreen.Receipt(r.id))
                }
            }
        }
    }
}

@Composable
fun ReceiptScreen(ctx: CCtx, id: String) {
    val r by ctx.sdk.observeOne(Entities.RECEIPTS, id, Receipt.serializer()).collectAsState(initial = null)
    AppScreen("Receipt", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val rc = r ?: return@AppScreen Empty("The receipt will appear after the next sync.")
        ScrollColumn {
            SectionCard("CHIPINGE RURAL DISTRICT COUNCIL – OFFICIAL RECEIPT") {
                KeyValue("Receipt no.", rc.number)
                KeyValue("Date", prettyDate(rc.createdAt))
                KeyValue("Account", rc.accountNumber)
                KeyValue("Received from", rc.payerName)
                KeyValue("For", rc.revenueHeadName)
                KeyValue("Amount", "${rc.currency} ${money(rc.amount)}")
                KeyValue("Method", "${rc.methodLabel} ${rc.reference}")
                KeyValue("Status", rc.statusLabel)
            }
            Text("Keep this receipt as proof of payment. It is also available on the council web portal.", fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

// ----------------------------------------------------------------- licences
@Composable
fun LicencesScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    AppScreen("My licences", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Apply / renew a licence", onClick = { ctx.go(CScreen.ApplyLicence) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No licences yet.") }
            items(list, key = { it.id }) { l ->
                SectionCard(l.businessName) {
                    Text("${l.number} · ${l.licenceTypeLabel} · ${l.premises}", fontSize = 12.sp, color = CrdcColors.Muted)
                    Row { StatusChip(l.statusLabel, l.status) }
                    if (l.expiryDate != null) KeyValue("Valid until", prettyDate(l.expiryDate))
                    if (l.rejectionReason.isNotBlank()) KeyValue("Reason", l.rejectionReason)
                    if (l.localNote != null) InfoBox(l.localNote!!)
                    if (l.status == "APPROVED" && l.bill != null) PrimaryButton("Pay licence fee $${money(l.fee)}", onClick = { ctx.go(CScreen.Pay(l.account, l.bill)) })
                }
            }
        }
    }
}

@Composable
fun ApplyLicenceScreen(ctx: CCtx) {
    val accounts by ctx.sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    var account by remember { mutableStateOf<ClientAccount?>(null) }
    if (account == null && accounts.isNotEmpty()) account = accounts.first()
    val props by ctx.sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    var stand by remember { mutableStateOf<Property?>(null) }
    var type by remember { mutableStateOf("SHOP") }
    var name by remember { mutableStateOf("") }
    var activity by remember { mutableStateOf("") }
    var premises by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    AppScreen("Apply for a licence", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (accounts.isEmpty()) {
                InfoBox("Link a council account first.")
                PrimaryButton("Link account", onClick = { ctx.go(CScreen.LinkAccount) })
                return@ScrollColumn
            }
            Picker("Council account", accounts, account, { "${it.accountNumber} – ${it.name}" }, { account = it })
            Picker("Stand / shop", props.filter { it.account == account?.id }, stand, { "Stand ${it.standNumber} ${it.areaName} ${it.businessName}" }, {
                stand = it
                if (name.isBlank()) name = it.businessName
                if (premises.isBlank()) premises = "Stand ${it.standNumber}, ${it.areaName.ifBlank { it.location }}"
            })
            ChoicePicker("Licence type", Choices.licenceTypes, type) { type = it }
            Field("Business / trading name", name, { name = it })
            Field("Business activity", activity, { activity = it })
            Field("Premises / stand / trading site", premises, { premises = it })
            Field("Ward", ward, { ward = it }, number = true)
            PrimaryButton("Submit application", enabled = name.isNotBlank() && premises.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val label = Choices.licenceTypes.first { it.first == type }.second
                val optimistic = buildJsonObject {
                    put("id", id); put("number", "(pending)"); put("licence_type", type); put("licence_type_label", label); put("account", account!!.id)
                    put("business_name", name); put("premises", premises); put("status", "APPLIED"); put("status_label", "Waiting to send")
                    put("updated_at", now); put("local_note", "Saved on your phone – it will be sent when you are online")
                }
                ctx.sdk.enqueue("licence.apply", "Licence application: $name", Entities.LICENCES, id, optimistic) {
                    put("id", id); put("account", account!!.id); stand?.let { put("property", it.id) }; put("licence_type", type); put("business_name", name)
                    put("business_activity", activity); put("premises", premises); ward.toIntOrNull()?.let { put("ward", it) }
                }
                ctx.back()
            })
            Text("Shops and food premises are inspected by the Environmental Health Officer. Once approved you pay the fee in the app and your licence is issued immediately.",
                fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

// ------------------------------------------------------ problems & feedback
@Composable
fun ProblemsScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.SERVICE_REQUESTS, ServiceRequest.serializer()).collectAsState(initial = emptyList())
    AppScreen("Problems I reported", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Report a problem", onClick = { ctx.go(CScreen.ReportProblem) })
        ListScreen {
            if (list.isEmpty()) item { Empty("Nothing reported yet.") }
            items(list, key = { it.id }) { s ->
                RowCard(s.categoryLabel, "${s.reference} · ${s.location}\n${s.resolution}", null, s.statusLabel, s.status, s.localNote)
            }
        }
    }
}

@Composable
fun ReportProblemScreen(ctx: CCtx) {
    var category by remember { mutableStateOf("WATER_FAULT") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    AppScreen("Report a problem", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("What is the problem?", Choices.serviceCategories, category) { category = it }
            Field("Where? (location / landmark)", location, { location = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("Describe the problem", description, { description = it }, singleLine = false, minLines = 4)
            PrimaryButton("Send report", enabled = location.isNotBlank() && description.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val label = Choices.serviceCategories.first { it.first == category }.second
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("category", category); put("category_label", label); put("location", location)
                    put("status", "REPORTED"); put("status_label", "Waiting to send"); put("updated_at", now)
                    put("local_note", "Saved on your phone – it will be sent when you are online")
                }
                ctx.sdk.enqueue("service_request.create", "Report: $label", Entities.SERVICE_REQUESTS, id, optimistic) {
                    put("id", id); put("category", category); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("description", description); put("captured_at", now)
                }
                ctx.back()
            })
            Text("Major water faults are attended within 24 hours (Client Charter).", fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

@Composable
fun FeedbackScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    AppScreen("Complaints & feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ New complaint, compliment or suggestion", onClick = { ctx.go(CScreen.NewFeedback) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No feedback yet.") }
            items(list, key = { it.id }) { c ->
                RowCard(c.subject, "${c.reference} · ${c.kindLabel} · ${prettyDate(c.createdAt)}" +
                    if (c.resolution.isNotBlank()) "\nResponse: ${c.resolution}" else "", null, c.statusLabel, c.status, c.localNote)
            }
        }
    }
}

@Composable
fun NewFeedbackScreen(ctx: CCtx) {
    var kind by remember { mutableStateOf("COMPLAINT") }
    var dept by remember { mutableStateOf("ADMIN") }
    var subject by remember { mutableStateOf("") }
    var details by remember { mutableStateOf("") }
    AppScreen("Feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Type", Choices.complaintKinds, kind) { kind = it }
            ChoicePicker("Which department?", Choices.departments, dept) { dept = it }
            Field("Subject", subject, { subject = it })
            Field("Details", details, { details = it }, singleLine = false, minLines = 4)
            PrimaryButton("Send", enabled = subject.isNotBlank() && details.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("kind", kind); put("subject", subject); put("details", details)
                    put("status", "RECEIVED"); put("status_label", "Waiting to send"); put("created_at", now); put("updated_at", now)
                    put("local_note", "Saved on your phone – it will be sent when you are online")
                }
                ctx.sdk.enqueue("complaint.create", "Feedback: $subject", Entities.COMPLAINTS, id, optimistic) {
                    put("id", id); put("kind", kind); put("department", dept); put("subject", subject); put("details", details); put("captured_at", now)
                }
                ctx.back()
            })
            Text("All complaints are acknowledged within 48 hours (Client Charter).", fontSize = 11.sp, color = CrdcColors.Muted)
        }
    }
}

@Composable
fun StandsScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.STANDS, StandApplication.serializer()).collectAsState(initial = emptyList())
    AppScreen("Stand applications", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Apply for a stand", onClick = { ctx.go(CScreen.ApplyStand) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No applications.") }
            items(list, key = { it.id }) { s ->
                RowCard("${s.standTypeLabel} stand", "${s.reference} · ${s.preferredLocation}" +
                    if (s.allocatedStand.isNotBlank()) "\nAllocated: ${s.allocatedStand}" else "", null, s.statusLabel, s.status)
            }
        }
    }
}

@Composable
fun ApplyStandScreen(ctx: CCtx) {
    var type by remember { mutableStateOf("RES") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var nid by remember { mutableStateOf("") }
    AppScreen("Apply for a stand", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Stand type", Choices.standTypes, type) { type = it }
            Field("Preferred location", location, { location = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("National ID", nid, { nid = it })
            PrimaryButton("Submit", enabled = location.isNotBlank() && nid.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("stand_type", type); put("preferred_location", location)
                    put("status", "RECEIVED"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("stand.create", "Stand application", Entities.STANDS, id, optimistic) {
                    put("id", id); put("stand_type", type); put("preferred_location", location); put("national_id", nid)
                    put("phone", ctx.me.phone); ward.toIntOrNull()?.let { put("ward", it) }
                }
                ctx.back()
            })
        }
    }
}

// --------------------------------------------------------------------- misc
@Composable
fun NotificationsScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.NOTIFICATIONS, AppNotification.serializer()).collectAsState(initial = emptyList())
    AppScreen("Notifications", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No notifications.") }
            items(list.sortedByDescending { it.createdAt }, key = { it.id }) { n ->
                RowCard(n.title, n.body + "\n" + prettyDate(n.createdAt), null, if (n.isRead) null else "New", "PENDING") {
                    if (!n.isRead) ctx.sdk.enqueue("notification.read", "Read notification", Entities.NOTIFICATIONS, n.id) { put("notification", n.id) }
                }
            }
        }
    }
}

@Composable
fun CharterScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.SERVICE_STANDARDS, ServiceStandard.serializer()).collectAsState(initial = emptyList())
    AppScreen("Client Charter 2026-2030", onBack = ctx::back) {
        ScrollColumn {
            SectionCard("Vision") { Text("A Provider of Responsive Quality Municipal Services by 2030.") }
            SectionCard("Our service standards") { list.forEach { KeyValue(it.service, it.standardText) } }
            SectionCard("Your rights") {
                Text("Quality and affordable services · Access to information · Fair and courteous treatment · Participation in development planning · Privacy and confidentiality · Transparent governance · Submit complaints and suggestions · Equal treatment without discrimination")
            }
            SectionCard("Your responsibilities") {
                Text("Pay rates and charges promptly · Observe Council by-laws · Protect Council infrastructure · Participate in development meetings · Provide accurate information · Protect the environment · Report service delivery challenges")
            }
            SectionCard("Contact") {
                Text("Chief Executive Officer, Chipinge Rural District Council\n858 E.D. Mnangagwa Street, P.O. Box 19, Chipinge\n+263 227 204 5631-5 · info@chipingerdc.gov.zw\nFacebook: chipingerdc · X: @chipingerdc")
            }
        }
    }
}

@Composable
fun SyncCentreScreen(ctx: CCtx) {
    val ops by ctx.sdk.outbox.collectAsState(initial = emptyList())
    AppScreen("Sync status", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item {
                SectionCard("This phone") {
                    KeyValue("Last sync", prettyDate(ctx.sync.lastSync))
                    KeyValue("Waiting to send", ctx.pending.toString())
                    ctx.sync.lastError?.let { InfoBox(it, CrdcColors.Warning) }
                    PrimaryButton("Sync now", busy = ctx.sync.running, onClick = { ctx.syncNow() })
                }
            }
            items(ops, key = { it.op_id }) { op ->
                SectionCard(op.summary) {
                    Text("Saved ${prettyDate(op.created_at)}", fontSize = 12.sp, color = CrdcColors.Muted)
                    if (op.status == "REJECTED") {
                        InfoBox("Not accepted: ${op.error}", CrdcColors.Danger)
                        SecondaryButton("Dismiss", { ctx.sdk.dismissRejected(op.op_id) })
                    } else Text("Waiting to send", color = CrdcColors.Blue, fontSize = 12.sp)
                }
            }
        }
    }
}
