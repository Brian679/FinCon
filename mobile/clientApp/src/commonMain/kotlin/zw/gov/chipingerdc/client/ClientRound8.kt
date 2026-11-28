package zw.gov.chipingerdc.client

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.PickedFile
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.AvailableStand
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.BuildingPlan
import zw.gov.chipingerdc.shared.model.Certificate
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Complaint
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.RegisterRequest
import zw.gov.chipingerdc.shared.model.RevenueHead
import zw.gov.chipingerdc.shared.model.StandApplication
import zw.gov.chipingerdc.shared.rememberFilePicker
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

private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.content ?: ""
private const val OFFLINE = "No connection. Try again when you are online."

/** Show / hide the balance. */
@Composable
fun EyeToggle(open: Boolean, onToggle: () -> Unit) {
    Box(Modifier.size(44.dp).clickable(onClick = onToggle), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(30.dp)) {
            val w = size.width
            val h = size.height
            val stroke = Stroke(width = w * 0.08f)
            drawOval(CrdcColors.Green, topLeft = Offset(w * 0.04f, h * 0.24f), size = Size(w * 0.92f, h * 0.52f), style = stroke)
            drawCircle(CrdcColors.Green, radius = w * 0.14f, center = Offset(w / 2, h / 2))
            if (!open) drawLine(CrdcColors.Green, Offset(w * 0.12f, h * 0.88f), Offset(w * 0.88f, h * 0.12f), strokeWidth = w * 0.08f)
        }
    }
}

// ---------------------------------------------------------------- dashboard
@Composable
fun ClientHome(ctx: CCtx) {
    val sdk = ctx.sdk
    val accounts by sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val licences by sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    val permits by sdk.observe(Entities.RESOURCE_PERMITS, JsonObject.serializer()).collectAsState(initial = emptyList())
    val certs by sdk.observe(Entities.CERTIFICATES, Certificate.serializer()).collectAsState(initial = emptyList())
    val stands by sdk.observe(Entities.STANDS, StandApplication.serializer()).collectAsState(initial = emptyList())
    val notices by sdk.observe(Entities.PUBLIC_NOTICES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val total = bills.filter { it.status in listOf("UNPAID", "PART") }.sumOf { it.outstanding.toDoubleOrNull() ?: 0.0 }
    var show by remember { mutableStateOf(ClientPrefs.showBalance) }
    AppScreen("Dashboard", sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            SectionCard("Outstanding balance") {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(if (show) "USD ${money(total.toString())}" else "USD ****", Modifier.weight(1f), fontSize = 26.sp, fontWeight = FontWeight.Bold,
                        color = if (show && total > 0) CrdcColors.Danger else CrdcColors.Green)
                    EyeToggle(show) { show = !show }
                }
                if (total > 0) PrimaryButton("Pay my bills", onClick = { ctx.go(CScreen.Accounts) })
            }
            if (accounts.isEmpty()) {
                PrimaryButton("Add my stand / shop / farm", color = CrdcColors.Blue, onClick = { ctx.go(CScreen.RegisterStand) })
                SecondaryButton("Add an existing council account", { ctx.go(CScreen.LinkAccount) })
            }
            val inProgress = certs.count { it.status in listOf("FEE_DUE", "PROCESSING") }
            val waiting = stands.firstOrNull { it.status in listOf("FEE_DUE", "RECEIVED", "SHORTLISTED", "APPROVED") }
            zw.gov.chipingerdc.shared.ui.AdaptiveGrid(listOf(
                { m -> Kpi("Licences", licences.count { it.status == "ISSUED" }.toString(), "valid", CrdcColors.Green, m) { ctx.go(CScreen.Licences) } },
                { m -> Kpi("Permits", permits.count { it.str("status") == "ACTIVE" }.toString(), "valid", CrdcColors.Green, m) { ctx.go(CScreen.Permits) } },
                { m ->
                    Kpi("Letters", certs.count { it.status == "ISSUED" }.toString(), if (inProgress > 0) "$inProgress in progress" else "issued",
                        if (inProgress > 0) CrdcColors.Warning else CrdcColors.Green, m) { ctx.go(CScreen.Certificates) }
                },
                { m ->
                    Kpi("Stand application", when (waiting?.status) {
                        "FEE_DUE" -> "Not submitted"; "APPROVED" -> "Approved"; null -> "–"; else -> waiting.waitingPosition?.let { "No. $it" } ?: "Waiting"
                    }, waiting?.reference ?: "none", if (waiting?.status in listOf("FEE_DUE", "APPROVED")) CrdcColors.Warning else CrdcColors.Green, m) {
                        ctx.go(CScreen.Stands)
                    }
                },
            ))
            notices.maxByOrNull { it.str("publish_from") }?.let { n ->
                RowCard("Notice: ${n.str("title")}", prettyDate(n.str("publish_from")), null, null, null) { ctx.go(CScreen.Notices) }
            }
        }
    }
}

// ----------------------------------------------------------------- my bills
/** My bills: only what is to be paid, grouped by stand / shop / farm. */
@Composable
fun AccountsScreen(ctx: CCtx) {
    val sdk = ctx.sdk
    val accounts by sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val props by sdk.observe(Entities.PROPERTIES, zw.gov.chipingerdc.shared.model.Property.serializer()).collectAsState(initial = emptyList())
    val rented by sdk.observe(Entities.TENANCIES, zw.gov.chipingerdc.shared.model.Tenancy.serializer()).collectAsState(initial = emptyList())
    val leases by sdk.observe(Entities.LEASES, zw.gov.chipingerdc.shared.model.Lease.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val fines by sdk.observe(Entities.FINES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val places = buildPlaces(accounts, props, rented, leases, bills, fines).filter { it.bills.isNotEmpty() }
    val total = places.sumOf { it.total }
    AppScreen("My bills", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (places.isEmpty()) item { Empty("No bills to pay.") }
            items(places, key = { it.key }) { p ->
                SectionCard(p.title) {
                    p.bills.sortedBy { it.dueDate }.forEach { b ->
                        RowCard(billLabel(b, fines), null, "$${money(b.outstanding)}", null, null) { ctx.go(CScreen.PayBills(listOf(b.id))) }
                    }
                    if (p.bills.size > 1) PrimaryButton("Pay $${money(p.total.toString())}", onClick = { ctx.go(CScreen.PayBills(p.bills.map { it.id })) })
                }
            }
        }
    }
}

// ------------------------------------------------------------------ sign up
@Composable
fun RegisterScreen(sdk: CouncilSdk, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var first by remember { mutableStateOf("") }
    var last by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var nid by remember { mutableStateOf("") }
    var p1 by remember { mutableStateOf("") }
    var p2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }
    AppScreen("Create account", onBack = onDone) {
        ScrollColumn {
            Field("First name", first, { first = it })
            Field("Surname", last, { last = it })
            Field("Username", username, { username = it })
            Field("Email", email, { email = it })
            Field("Mobile number", phone, { phone = it })
            Field("National ID", nid, { nid = it.uppercase() })
            Field("Password (min. 8 characters)", p1, { p1 = it }, password = true)
            Field("Confirm password", p2, { p2 = it }, password = true)
            msg?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Create account", busy = busy, enabled = listOf(first, last, username, phone, nid, p1).all { it.isNotBlank() } && p1 == p2, onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        sdk.register(sdk.session.baseUrl, RegisterRequest(first, last, username, email, phone, nid, "", p1, p2))
                        sdk.login(sdk.session.baseUrl, username, p1)
                    }.onFailure { msg = it.message ?: OFFLINE }
                    busy = false
                }
            })
        }
    }
}

// ----------------------------------------------------------------- settings
@Composable
fun ProfileScreen(ctx: CCtx) {
    val me = ctx.me
    val scope = rememberCoroutineScope()
    var first by remember { mutableStateOf(me.firstName.ifBlank { me.fullName.substringBeforeLast(" ") }) }
    var last by remember { mutableStateOf(me.lastName.ifBlank { me.fullName.substringAfterLast(" ", "") }) }
    var phone by remember { mutableStateOf(me.phone) }
    var email by remember { mutableStateOf(me.email) }
    var nid by remember { mutableStateOf(me.nationalId) }
    var ward by remember { mutableStateOf(me.ward?.toString() ?: "") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    AppScreen("My profile", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            KeyValue("Username", me.username)
            Field("First name", first, { first = it })
            Field("Surname", last, { last = it })
            Field("Mobile number", phone, { phone = it })
            Field("Email", email, { email = it })
            Field("National ID", nid, { nid = it.uppercase() })
            Field("Ward", ward, { ward = it }, number = true)
            msg?.let { InfoBox(it.first, if (it.second) CrdcColors.Success else CrdcColors.Danger) }
            PrimaryButton("Save", busy = busy, enabled = first.isNotBlank() && last.isNotBlank() && phone.isNotBlank(), onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        ctx.sdk.updateProfile(buildJsonObject {
                            put("first_name", first.trim()); put("last_name", last.trim()); put("phone", phone.trim()); put("email", email.trim())
                            put("national_id", nid.trim()); put("ward", ward.trim())
                        })
                    }.onSuccess { msg = "Saved." to true }.onFailure { msg = (it.message ?: OFFLINE) to false }
                    busy = false
                }
            })
            SecondaryButton("Change password", { ctx.go(CScreen.ChangePassword) })
        }
    }
}

// ------------------------------------------------------- existing account
@Composable
fun LinkAccountScreen(ctx: CCtx) {
    val scope = rememberCoroutineScope()
    var number by remember { mutableStateOf("") }
    var verifier by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Add an existing account", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Council account number (e.g. CR2026-00001)", number, { number = it.uppercase() })
            Field("Phone number or National ID on the account", verifier, { verifier = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Add account", busy = busy, enabled = number.isNotBlank() && verifier.isNotBlank(), onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        val acc = ctx.sdk.postJson("client/link-account/", buildJsonObject { put("account_number", number.trim()); put("verifier", verifier.trim()) })
                        ctx.sdk.store.upsert(Entities.ACCOUNTS, acc)
                        listOf(Entities.ACCOUNTS, Entities.PROPERTIES, Entities.BILLS, Entities.RECEIPTS, Entities.LICENCES).forEach { ctx.sdk.store.resetCursor(it) }
                        ctx.sdk.sync.sync()
                        ctx.back()
                    }.onFailure { error = it.message ?: OFFLINE }
                    busy = false
                }
            })
        }
    }
}

// --------------------------------------------------------------- messages
@Composable
fun FeedbackScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.COMPLAINTS, Complaint.serializer()).collectAsState(initial = emptyList())
    AppScreen("Feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { PrimaryButton("+ Send feedback", onClick = { ctx.go(CScreen.NewFeedback) }) }
            if (list.isEmpty()) item { Empty("No feedback yet.") }
            items(list.sortedByDescending { it.createdAt }, key = { it.id }) { c ->
                RowCard(c.subject, "${c.reference} · ${prettyDate(c.createdAt)}" + if (c.resolution.isNotBlank()) "\nCouncil: ${c.resolution}" else "",
                    null, c.statusLabel, c.status, c.localNote)
            }
        }
    }
}

@Composable
fun NewFeedbackScreen(ctx: CCtx) {
    var message by remember { mutableStateOf("") }
    AppScreen("Send feedback", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Your feedback", message, { message = it }, singleLine = false, minLines = 6)
            PrimaryButton("Send", enabled = message.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val text = message.trim()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("subject", if (text.length > 60) text.take(57) + "…" else text); put("details", text)
                    put("status", "RECEIVED"); put("status_label", "Waiting to send"); put("created_at", now); put("updated_at", now)
                }
                ctx.sdk.enqueue("complaint.create", "Feedback", Entities.COMPLAINTS, id, opt) {
                    put("id", id); put("details", text); put("captured_at", now)
                }
                ctx.back()
            })
        }
    }
}

// --------------------------------------------------------- stand applications
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
                    KeyValue("Area", s.areaName.ifBlank { s.preferredLocation })
                    Row { StatusChip(s.statusLabel, if (s.status == "FEE_DUE") "WAITING" else s.status) }
                    when (s.status) {
                        "FEE_DUE" -> if (s.feeBill != null && !paid(s.feeBill))
                            PrimaryButton("Pay $${money(s.fee ?: "0")} and submit", onClick = { ctx.go(CScreen.PayBills(listOf(s.feeBill))) })
                        "RECEIVED", "SHORTLISTED" -> s.waitingPosition?.let { KeyValue("Waiting list", "No. $it") }
                        "APPROVED" -> {
                            KeyValue("Stand reserved", s.allocatedStand)
                            if (s.depositBill != null && !(s.depositPaid || paid(s.depositBill)))
                                PrimaryButton("Pay for the stand $${money(s.deposit ?: "0")}", onClick = { ctx.go(CScreen.PayBills(listOf(s.depositBill))) })
                        }
                        "ALLOCATED" -> KeyValue("Stand number", s.allocatedStand)
                    }
                }
            }
        }
    }
}

@Composable
fun ApplyStandScreen(ctx: CCtx) {
    val avail by ctx.sdk.observe(Entities.AVAILABLE_STANDS, AvailableStand.serializer()).collectAsState(initial = emptyList())
    val heads by ctx.sdk.observe(Entities.REVENUE_HEADS, RevenueHead.serializer()).collectAsState(initial = emptyList())
    var type by remember { mutableStateOf("RES") }
    var area by remember { mutableStateOf<Pair<String, String>?>(null) }
    val areas = avail.filter { it.status == "AVAILABLE" && it.standType == type }.groupBy { it.area }
        .map { (id, l) -> id to "${l.first().areaName} – ${l.size} available" }.sortedBy { it.second }
    val fee = heads.firstOrNull { it.code == "STAND-APP" }?.defaultAmount ?: "0"
    AppScreen("Apply for a stand", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Stand type", Choices.standTypes, type) { type = it; area = null }
            if (areas.isEmpty()) Empty("No stands of this type are available right now.")
            else Picker("Area", areas, area, { it.second }, { area = it })
            KeyValue("Waiting-list fee", "USD ${money(fee)}")
            PrimaryButton("Apply", enabled = area != null, onClick = {
                val id = ctx.sdk.newId()
                val a = area!!
                val name = a.second.substringBefore(" – ")
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("stand_type", type); put("area", a.first); put("area_name", name)
                    put("preferred_location", name); put("status", "FEE_DUE"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("stand.create", "Stand application", Entities.STANDS, id, optimistic) {
                    put("id", id); put("stand_type", type); put("area", a.first); put("national_id", ctx.me.nationalId); put("phone", ctx.me.phone)
                }
                listOf(Entities.ACCOUNTS, Entities.BILLS).forEach { ctx.sdk.store.resetCursor(it) }
                ctx.back()
            })
        }
    }
}

// ----------------------------------------------------------- building plans
private suspend fun uploadPlanFile(sdk: CouncilSdk, planId: String, file: PickedFile) {
    val res = sdk.uploadFile("plans/$planId/drawing/", "file", file.name, file.bytes, file.mime)
    sdk.store.upsert(Entities.BUILDING_PLANS, res)
}

@Composable
fun PlansScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.BUILDING_PLANS, BuildingPlan.serializer()).collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()
    var target by remember { mutableStateOf<String?>(null) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    val pick = rememberFilePicker { f ->
        val id = target
        if (f != null && id != null) scope.launch {
            runCatching { uploadPlanFile(ctx.sdk, id, f) }.onSuccess { msg = "Plan file sent." to true }.onFailure { msg = (it.message ?: OFFLINE) to false }
        }
    }
    AppScreen("My building plans", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { PrimaryButton("+ Submit a building plan", onClick = { ctx.go(CScreen.NewPlan) }) }
            msg?.let { m -> item { InfoBox(m.first, if (m.second) CrdcColors.Success else CrdcColors.Danger) } }
            if (list.isEmpty()) item { Empty("No building plans.") }
            items(list, key = { it.id }) { p ->
                SectionCard("${p.developmentTypeLabel.ifBlank { "Building plan" }} – stand ${p.standNumber}") {
                    KeyValue("Reference", p.reference)
                    Row { StatusChip(p.statusLabel.ifBlank { "Waiting to send" }, p.status) }
                    KeyValue("Plan file", p.drawingName.ifBlank { "Not attached" })
                    if (p.decisionNotes.isNotBlank()) KeyValue("Council decision", p.decisionNotes)
                    if (p.bill != null && p.billStatus != "PAID") PrimaryButton("Pay plan fee $${money(p.fee)}", onClick = { ctx.go(CScreen.PayBills(listOf(p.bill!!))) })
                    if (p.drawingName.isBlank() && p.reference != "(sending)") SecondaryButton("Attach plan file", { target = p.id; pick() })
                }
            }
        }
    }
}

@Composable
fun NewPlanScreen(ctx: CCtx) {
    var stand by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("RES") }
    var description by remember { mutableStateOf("") }
    var area by remember { mutableStateOf("") }
    var file by remember { mutableStateOf<PickedFile?>(null) }
    val pick = rememberFilePicker { f -> if (f != null) file = f }
    AppScreen("Submit building plan", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Stand number", stand, { stand = it }); Field("Location", location, { location = it }); Field("Ward", ward, { ward = it }, number = true)
            ChoicePicker("Development", Choices.devTypes, type) { type = it }
            Field("Description (rooms, size, materials)", description, { description = it }, singleLine = false, minLines = 3)
            Field("Floor area (m²)", area, { area = it }, number = true)
            KeyValue("Plan file", file?.name ?: "None chosen")
            SecondaryButton(if (file == null) "Choose plan file (PDF / photo)" else "Choose another file", { pick() })
            PrimaryButton("Submit", enabled = stand.isNotBlank() && location.isNotBlank() && description.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("stand_number", stand); put("location", location); put("development_type", type)
                    put("status", "SUBMITTED"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("plan.create", "Building plan: stand $stand", Entities.BUILDING_PLANS, id, opt) {
                    put("id", id); put("stand_number", stand); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("development_type", type); put("description", description); put("floor_area", area.ifBlank { "0" })
                }
                file?.let { f -> ctx.sdk.scope.launch { runCatching { ctx.sdk.sync.sync(); uploadPlanFile(ctx.sdk, id, f) } } }
                ctx.back()
            })
        }
    }
}


// ------------------------------------------------------------ app settings
/** Preferences kept on this phone. */
object ClientPrefs {
    var showBalance by mutableStateOf(false)
    var autoSync by mutableStateOf(true)
    var largeText by mutableStateOf(false)

    fun load(sdk: CouncilSdk) {
        showBalance = sdk.store.value("pref.show_balance") == "1"
        autoSync = sdk.store.value("pref.auto_sync") != "0"
        largeText = sdk.store.value("pref.large_text") == "1"
    }

    fun save(sdk: CouncilSdk) {
        sdk.store.setValue("pref.show_balance", if (showBalance) "1" else "0")
        sdk.store.setValue("pref.auto_sync", if (autoSync) "1" else "0")
        sdk.store.setValue("pref.large_text", if (largeText) "1" else "0")
        if (autoSync) sdk.sync.startAuto(sdk.scope) else sdk.sync.stopAuto()
    }
}

@Composable
private fun Toggle(label: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { onChange(!on) }, verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), fontSize = 15.sp)
        androidx.compose.material3.Switch(checked = on, onCheckedChange = onChange)
    }
}

@Composable
fun AppSettingsScreen(ctx: CCtx) {
    AppScreen("Settings", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            SectionCard("Display") {
                Toggle("Show my balance on the dashboard", ClientPrefs.showBalance) { ClientPrefs.showBalance = it; ClientPrefs.save(ctx.sdk) }
                Toggle("Larger text", ClientPrefs.largeText) { ClientPrefs.largeText = it; ClientPrefs.save(ctx.sdk) }
            }
            SectionCard("About") {
                KeyValue("App", "Chipinge RDC online services")
                KeyValue("Version", "1.0")
                KeyValue("Phone", zw.gov.chipingerdc.shared.platformName)
            }
        }
    }
}
