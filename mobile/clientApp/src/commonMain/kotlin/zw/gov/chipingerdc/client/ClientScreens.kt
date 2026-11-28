package zw.gov.chipingerdc.client

import kotlinx.datetime.toLocalDateTime
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.padding
import zw.gov.chipingerdc.shared.model.shopStatus
import zw.gov.chipingerdc.shared.model.Lease
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
import zw.gov.chipingerdc.shared.model.Tenancy
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.Caption
import zw.gov.chipingerdc.shared.ui.IndexModule
import zw.gov.chipingerdc.shared.ui.IndexRow
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
    var rel by remember { mutableStateOf("NONE") }
    var stand by remember { mutableStateOf("") }
    var place by remember { mutableStateOf("") }
    var business by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    AppScreen("Create account", onBack = onDone) {
        ScrollColumn {
            Field("First name", first, { first = it })
            Field("Surname", last, { last = it })
            Field("Username", username, { username = it })
            Field("Email", email, { email = it })
            Field("Mobile number", phone, { phone = it })
            Field("National ID", nid, { nid = it })
            Field("Ward (optional)", ward, { ward = it }, number = true)
            Caption("Your stand / property")
            ChoicePicker("How are you connected to a stand?", Choices.relationships, rel) { rel = it }
            if (rel != "NONE") {
                Field("Stand number", stand, { stand = it })
                Field("Township, village or growth point", place, { place = it })
                if (rel != "OWNER") Field("Shop / business name (if any)", business, { business = it })
            }
            Field("Password (min. 8 characters)", p1, { p1 = it }, password = true)
            Field("Confirm password", p2, { p2 = it }, password = true)
            msg?.let { InfoBox(it.first, if (it.second) CrdcColors.Success else CrdcColors.Danger) }
            PrimaryButton("Create account", busy = busy, enabled = listOf(first, last, username, phone, nid, p1).all { it.isNotBlank() } && p1 == p2 && (rel == "NONE" || stand.isNotBlank()), onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        sdk.register(sdk.session.baseUrl, RegisterRequest(first, last, username, email, phone, nid, ward, p1, p2,
                            relationship = rel, standNumber = stand.takeIf { rel != "NONE" } ?: "", location = place, businessName = business))
                        sdk.login(sdk.session.baseUrl, username, p1)
                    }.onFailure { msg = (it.message ?: ONLINE_ONLY) to false }
                    busy = false
                }
            })
        }
    }
}

// --------------------------------------------------------------------- menu
/** The menu (menu icon, top left), grouped by what a resident wants to do. */
@Composable
fun ClientMenu(ctx: CCtx) {
    val sdk = ctx.sdk
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val certs by sdk.observe(Entities.CERTIFICATES, zw.gov.chipingerdc.shared.model.Certificate.serializer()).collectAsState(initial = emptyList())
    var find by remember { mutableStateOf("") }
    val modules = listOf(
        "Home" to listOf(IndexRow("Dashboard", 0, { ctx.go(CScreen.Home) })),
        "Payments" to listOf(
            IndexRow("My bills", bills.count { it.status in listOf("UNPAID", "PART") }, { ctx.go(CScreen.Accounts) }),
            IndexRow("Payment history", 0, { ctx.go(CScreen.Receipts) }),
            IndexRow("Statements", 0, { ctx.go(CScreen.Statements) }),
        ),
        "My property" to listOf(
            IndexRow("My stands, shops & farms", 0, { ctx.go(CScreen.MyStands) }, { ctx.go(CScreen.RegisterStand) }),
            IndexRow("Apply for a stand", 0, { ctx.go(CScreen.Stands) }, { ctx.go(CScreen.ApplyStand) }),
            IndexRow("Building plans", 0, { ctx.go(CScreen.Plans) }, { ctx.go(CScreen.NewPlan) }),
        ),
        "Licences & permits" to listOf(
            IndexRow("Shop & business licences", 0, { ctx.go(CScreen.Licences) }, { ctx.go(CScreen.ApplyLicence) }),
            IndexRow("Sand & natural resource permits", 0, { ctx.go(CScreen.Permits) }, { ctx.go(CScreen.ApplyPermit) }),
        ),
        "Letters & certificates" to listOf(
            IndexRow("Proof of residence, rates clearance, cession, burial order", certs.count { it.status == "FEE_DUE" },
                { ctx.go(CScreen.Certificates) }, { ctx.go(CScreen.RequestCertificate) }),
        ),
        "Help & feedback" to listOf(
            IndexRow("Report a problem", 0, { ctx.go(CScreen.Problems) }, { ctx.go(CScreen.ReportProblem) }),
            IndexRow("Complaints & suggestions", 0, { ctx.go(CScreen.Feedback) }, { ctx.go(CScreen.NewFeedback) }),
            IndexRow("Council notices", 0, { ctx.go(CScreen.Notices) }),
        ),
    )
    androidx.compose.foundation.layout.Column(
        Modifier.fillMaxWidth().verticalScroll(androidx.compose.foundation.rememberScrollState()).padding(12.dp),
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(12.dp),
    ) {
        Field("Filter", find, { find = it })
        modules.map { (t, rows) -> t to rows.filter { find.isBlank() || it.label.contains(find.trim(), ignoreCase = true) || t.contains(find.trim(), ignoreCase = true) } }
            .filter { it.second.isNotEmpty() }
            .forEach { (t, rows) -> IndexModule(t, rows) }
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
            if (bill != null) KeyValue("Bill", "${bill.number} – ${bill.description}")
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
                        Text("Approve on ${p.phone}", fontWeight = FontWeight.SemiBold)
                        if (p.provider == "simulated") {
                            InfoBox("Test mode", CrdcColors.Warning)
                            PrimaryButton("Confirm (test mode)", onClick = { scope.launch { call("confirm") } })
                        } else PrimaryButton("I have approved – check status", onClick = { scope.launch { call("check") } })
                        SecondaryButton("Cancel payment", { scope.launch { call("cancel") } })
                    }
                    "PAID" -> {
                        val nums = p.receiptNumbers.ifEmpty { listOfNotNull(p.receiptNumber) }
                        InfoBox("Paid. " + if (nums.size > 1) "${nums.size} receipts: ${nums.joinToString(", ")}" else "Receipt ${nums.firstOrNull() ?: ""}", CrdcColors.Success)
                        if (nums.size > 1) PrimaryButton("Payment history", onClick = { ctx.back(); ctx.go(CScreen.Receipts) })
                        else PrimaryButton("View receipt", onClick = { p.receipt?.let { ctx.go(CScreen.Receipt(it)) } })
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
                    if (l.status == "APPROVED") {
                        l.stillToPay.forEach { KeyValue("${it.label} to pay", "USD ${money(it.amount)}") }
                        val feeOwed = l.stillToPay.any { it.label == "Licence fee" }
                        val total = l.stillToPay.sumOf { it.amount.toDoubleOrNull() ?: 0.0 }
                        if (feeOwed && l.bill != null) PrimaryButton("Pay licence fee $${money(l.fee)}", onClick = { l.bill?.let { ctx.go(CScreen.PayBills(listOf(it))) } })
                        else if (total > 0) PrimaryButton("Pay what is owing $${money(total.toString())}", onClick = { ctx.go(CScreen.Accounts) })
                    }
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
    val rented by ctx.sdk.observe(Entities.TENANCIES, Tenancy.serializer()).collectAsState(initial = emptyList())
    var stand by remember { mutableStateOf<Property?>(null) }
    var type by remember { mutableStateOf("SHOP") }
    var name by remember { mutableStateOf("") }
    var activity by remember { mutableStateOf("") }
    var premises by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    AppScreen("Apply for a licence", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (accounts.isEmpty()) {
                PrimaryButton("Link a council account", onClick = { ctx.go(CScreen.LinkAccount) })
                return@ScrollColumn
            }
            Picker("Council account", accounts, account, { "${it.accountNumber} – ${it.name}" }, { account = it })
            val places = props.filter { it.account == account?.id }.map { Triple(it.id, "Stand ${it.standNumber} ${it.areaName} ${it.businessName}".trim(), it) } +
                rented.filter { it.tenant == account?.id && it.isActive }.map {
                    Triple(it.property, "Stand ${it.standNumber} ${it.areaName} (rented)", Property(id = it.property, standNumber = it.standNumber,
                        areaName = it.areaName, location = it.location, businessName = it.businessName))
                }
            Picker("Stand / shop", places, places.firstOrNull { it.first == stand?.id }, { it.second }, { (_, _, p) ->
                stand = p
                if (name.isBlank()) name = p.businessName
                if (premises.isBlank()) premises = "Stand ${p.standNumber}, ${p.areaName.ifBlank { p.location }}"
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
        }
    }
}

@Composable
fun StandsScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.STANDS, StandApplication.serializer()).collectAsState(initial = emptyList())
    val bills by ctx.sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    fun paid(id: String?) = id != null && bills.firstOrNull { it.id == id }?.status == "PAID"
    AppScreen("Stand applications", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { PrimaryButton("Apply for a stand", onClick = { ctx.go(CScreen.ApplyStand) }) }
            if (list.isEmpty()) item { Empty("No applications.") }
            items(list.sortedByDescending { it.createdAt }, key = { it.id }) { s ->
                SectionCard("${s.standTypeLabel.ifBlank { "Stand" }} stand · ${s.reference}") {
                    KeyValue("Place", s.preferredLocation + (s.ward?.let { ", ward $it" } ?: ""))
                    Row { StatusChip(s.statusLabel, s.status) }
                    when (s.status) {
                        "FEE_DUE" -> {
                            if (s.feeBill != null && !paid(s.feeBill)) PrimaryButton("Pay $${money(s.fee ?: "0")} waiting-list fee", onClick = { ctx.go(CScreen.PayBills(listOf(s.feeBill))) })
                        }
                        "RECEIVED", "SHORTLISTED" -> s.waitingPosition?.let {
                            KeyValue("Waiting list", "No. $it" + (s.joinedWaitingListAt?.let { d -> " since ${prettyDate(d)}" } ?: ""))
                        }
                        "ALLOCATED" -> {
                            KeyValue("Allocated stand", s.allocatedStand)
                            if (s.depositBill != null) {
                                if (s.depositPaid || paid(s.depositBill)) Text("Deposit of $${money(s.deposit ?: "0")} paid.", fontSize = 13.sp, color = CrdcColors.Success)
                                else PrimaryButton("Pay deposit $${money(s.deposit ?: "0")}", onClick = { ctx.go(CScreen.PayBills(listOf(s.depositBill))) })
                            }
                        }
                    }
                }
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
                    put("status", "FEE_DUE"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("stand.create", "Stand application", Entities.STANDS, id, optimistic) {
                    put("id", id); put("stand_type", type); put("preferred_location", location); put("national_id", nid)
                    put("phone", ctx.me.phone); ward.toIntOrNull()?.let { put("ward", it) }
                }
                // the waiting-list fee bill (and the account it is on) arrive with the next sync
                listOf(Entities.ACCOUNTS, Entities.BILLS).forEach { ctx.sdk.store.resetCursor(it) }
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
