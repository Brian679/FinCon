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
            IndexRow("Letters & certificates", certs.count { it.status == "FEE_DUE" },
                { ctx.go(CScreen.Certificates) }, { ctx.go(CScreen.RequestCertificate) }),
        ),
        "Help & feedback" to listOf(
            IndexRow("Report a problem", 0, { ctx.go(CScreen.Problems) }, { ctx.go(CScreen.ReportProblem) }),
            IndexRow("Feedback", 0, { ctx.go(CScreen.Feedback) }, { ctx.go(CScreen.NewFeedback) }),
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
            Picker("Account", accounts, account, { "${it.accountNumber} – ${it.name}" }, { account = it })
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
                            PrimaryButton("Confirm payment", onClick = { scope.launch { call("confirm") } })
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

