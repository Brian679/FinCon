package zw.gov.chipingerdc.client

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import zw.gov.chipingerdc.shared.model.AppJson
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.Certificate
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Lease
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.OnlinePayment
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.Receipt
import zw.gov.chipingerdc.shared.model.StandApplication
import zw.gov.chipingerdc.shared.model.Tenancy
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.Caption
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.content ?: ""
private fun String.num() = toDoubleOrNull() ?: 0.0
private fun Bill.isDue() = status in listOf("UNPAID", "PART") && outstanding.num() > 0

/** Everything a resident is connected to – own stands and houses, shops, farms, rented places, council leases – with what is owed on each. */
data class Place(val key: String, val kind: String, val title: String, val subtitle: String, val bills: List<Bill>) {
    val total: Double get() = bills.sumOf { it.outstanding.num() }
}

fun buildPlaces(accounts: List<ClientAccount>, props: List<Property>, rented: List<Tenancy>, leases: List<Lease>, bills: List<Bill>,
                fines: List<JsonObject>): List<Place> {
    val due = bills.filter { it.isDue() }
    val fineBills = fines.map { it.str("bill") }.filter { it.isNotBlank() }.toSet()
    val used = mutableSetOf<String>()
    fun take(pred: (Bill) -> Boolean) = due.filter { it.id !in used && it.id !in fineBills && pred(it) }.also { l -> used += l.map { it.id } }
    fun acc(id: String) = accounts.firstOrNull { it.id == id }?.accountNumber ?: ""
    val out = mutableListOf<Place>()
    props.sortedWith(compareBy({ if (it.hectares != null || it.landUse == "AGR") 2 else if (it.landUse == "COM" || it.businessName.isNotBlank()) 1 else 0 }, { it.standNumber }))
        .forEach { p ->
            val farm = p.hectares != null || p.landUse == "AGR"
            val shop = !farm && (p.landUse == "COM" || p.businessName.isNotBlank())
            val where = p.areaName.ifBlank { p.location }
            val (kind, title) = when {
                farm -> "FARM" to "Farm ${p.standNumber}"
                shop -> "SHOP" to "${p.businessName.ifBlank { "Shop" }} · Stand ${p.standNumber}"
                else -> "HOUSE" to "${p.landUseLabel.ifBlank { "House" }} · Stand ${p.standNumber}"
            }
            out += Place(p.id, kind, title, "$where${p.hectares?.let { " · $it ha" } ?: ""} · ${acc(p.account)}", take { it.property == p.id })
        }
    rented.filter { it.isActive }.forEach { t ->
        out += Place("t" + t.id, "RENTED", "Rented: ${t.businessName.ifBlank { "Stand ${t.standNumber}" }}",
            "Stand ${t.standNumber} · ${t.areaName.ifBlank { t.location }} · ${t.tenantAccountNumber}", take { it.property == t.property && it.account == t.tenant })
    }
    leases.forEach { l ->
        out += Place("l" + l.id, "LEASE", "Lease: ${l.premisesName}", "${l.number} · $${money(l.monthlyRent)} a month",
            take { it.property == l.premises && it.account == l.lessee })
    }
    val fineList = due.filter { it.id in fineBills }
    if (fineList.isNotEmpty()) out += Place("fines", "FINES", "Fines", "${fineList.size} unpaid", fineList)
    val other = take { true }
    if (other.isNotEmpty()) out += Place("other", "OTHER", "Other charges", "Licences, applications, permits, letters", other)
    return out
}

fun billLabel(b: Bill, fines: List<JsonObject>): String {
    fines.firstOrNull { it.str("bill") == b.id }?.let { return "Fine ${it.str("reference")}: ${it.str("offence_name").substringBefore(" (")}" }
    return b.description.substringBefore(" – ").substringBefore(" - Stand").ifBlank { b.number }
}

@Composable
private fun observeMoney(ctx: CCtx): MoneyState {
    val sdk = ctx.sdk
    val accounts by sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    val rented by sdk.observe(Entities.TENANCIES, Tenancy.serializer()).collectAsState(initial = emptyList())
    val leases by sdk.observe(Entities.LEASES, Lease.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val fines by sdk.observe(Entities.FINES, JsonObject.serializer()).collectAsState(initial = emptyList())
    return MoneyState(accounts, buildPlaces(accounts, props, rented, leases, bills, fines), fines)
}

private class MoneyState(val accounts: List<ClientAccount>, val places: List<Place>, val fines: List<JsonObject>) {
    val total get() = places.sumOf { it.total }
    val dueIds get() = places.flatMap { p -> p.bills.map { it.id } }
}

// ---------------------------------------------------------------- dashboard
/** The dashboard: what is owed (everything, by place) and the state of the resident's licences, permits and applications. */
@Composable
fun ClientHome(ctx: CCtx) {
    val m = observeMoney(ctx)
    val licences by ctx.sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    val permits by ctx.sdk.observe(Entities.RESOURCE_PERMITS, JsonObject.serializer()).collectAsState(initial = emptyList())
    val certs by ctx.sdk.observe(Entities.CERTIFICATES, Certificate.serializer()).collectAsState(initial = emptyList())
    val stands by ctx.sdk.observe(Entities.STANDS, StandApplication.serializer()).collectAsState(initial = emptyList())
    val notices by ctx.sdk.observe(Entities.PUBLIC_NOTICES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val placesOnly = m.places.filter { it.kind !in listOf("FINES", "OTHER") }
    AppScreen("Dashboard", sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("To pay", "$${money(m.total.toString())}", "${m.dueIds.size} bill(s)", if (m.total > 0) CrdcColors.Danger else CrdcColors.Green,
                    Modifier.weight(1f)) { ctx.go(CScreen.Accounts) }
                Kpi("My places", placesOnly.size.toString(), "stands, shops, farms", CrdcColors.Green, Modifier.weight(1f)) { ctx.go(CScreen.MyStands) }
            }
            if (m.total > 0) PrimaryButton("Pay everything $${money(m.total.toString())}", onClick = { ctx.go(CScreen.PayBills(m.dueIds)) })
            if (placesOnly.isEmpty()) {
                PrimaryButton("Add my stand / shop / farm", color = CrdcColors.Blue, onClick = { ctx.go(CScreen.RegisterStand) })
                SecondaryButton("Link with account number", { ctx.go(CScreen.LinkAccount) })
            } else SectionCard("My places") {
                placesOnly.forEach { p ->
                    RowCard(p.title, p.subtitle, if (p.total > 0) "$${money(p.total.toString())}" else "Paid up", null, null) { ctx.go(CScreen.Accounts) }
                }
            }
            val letters = certs.count { it.status in listOf("FEE_DUE", "PROCESSING") }
            val waiting = stands.firstOrNull { it.status in listOf("FEE_DUE", "RECEIVED", "SHORTLISTED") }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Licences", licences.count { it.status == "ISSUED" }.toString(), "valid", CrdcColors.Green, Modifier.weight(1f)) { ctx.go(CScreen.Licences) }
                Kpi("Permits", permits.count { it.str("status") == "ACTIVE" }.toString(), "valid", CrdcColors.Green, Modifier.weight(1f)) { ctx.go(CScreen.Permits) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kpi("Letters", certs.count { it.status == "ISSUED" }.toString(), if (letters > 0) "$letters in progress" else "issued",
                    if (letters > 0) CrdcColors.Warning else CrdcColors.Green, Modifier.weight(1f)) { ctx.go(CScreen.Certificates) }
                Kpi("Stand waiting list", waiting?.waitingPosition?.let { "No. $it" } ?: if (waiting != null) "Fee due" else "–",
                    waiting?.reference ?: "not applied", if (waiting?.status == "FEE_DUE") CrdcColors.Warning else CrdcColors.Green, Modifier.weight(1f)) {
                    ctx.go(CScreen.Stands)
                }
            }
            notices.maxByOrNull { it.str("publish_from") }?.let { n ->
                RowCard("Notice: ${n.str("title")}", prettyDate(n.str("publish_from")), null, null, null) { ctx.go(CScreen.Notices) }
            }
        }
    }
}

// ----------------------------------------------------------------- my bills
/** My bills: the balance on every place the resident is connected to, bill by bill, with fines in the same list. */
@Composable
fun AccountsScreen(ctx: CCtx) {
    val m = observeMoney(ctx)
    AppScreen("My bills", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { Caption(if (m.total > 0) "Total to pay: $${money(m.total.toString())}" else "Nothing to pay") }
            if (m.total > 0) item { PrimaryButton("Pay everything $${money(m.total.toString())}", onClick = { ctx.go(CScreen.PayBills(m.dueIds)) }) }
            if (m.places.isEmpty()) item { Empty("No stands, shops or farms linked yet.") }
            items(m.places, key = { it.key }) { p ->
                SectionCard(p.title) {
                    Text(p.subtitle, fontSize = 12.sp, color = CrdcColors.Muted)
                    if (p.bills.isEmpty()) Text("Paid up", color = CrdcColors.Success, fontWeight = FontWeight.SemiBold)
                    p.bills.sortedBy { it.dueDate }.forEach { b ->
                        RowCard(billLabel(b, m.fines), "${b.number}${if (b.dueDate.isNotBlank()) " · due ${prettyDate(b.dueDate)}" else ""}",
                            "$${money(b.outstanding)}", null, null) { ctx.go(CScreen.PayBills(listOf(b.id))) }
                    }
                    if (p.bills.size > 1) PrimaryButton("Pay $${money(p.total.toString())}", onClick = { ctx.go(CScreen.PayBills(p.bills.map { it.id })) })
                }
            }
            item { SecondaryButton("Statements", { ctx.go(CScreen.Statements) }) }
            item { SecondaryButton("Add a stand / shop / farm", { ctx.go(CScreen.RegisterStand) }) }
            item { SecondaryButton("Add a fine by its number", { ctx.go(CScreen.FindFine) }) }
        }
    }
}

// -------------------------------------------------------------- pay bills
/** Pays one bill, one place's bills or everything at once – one mobile-money prompt, a receipt for every bill. */
@Composable
fun PayBillsScreen(ctx: CCtx, ids: List<String>) {
    val sdk = ctx.sdk
    val scope = rememberCoroutineScope()
    val all by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val fines by sdk.observe(Entities.FINES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val bills = all.filter { it.id in ids && it.isDue() }
    val total = bills.sumOf { it.outstanding.num() }
    var method by remember { mutableStateOf("ECOCASH") }
    var phone by remember { mutableStateOf(ctx.me.phone) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Pay", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            SectionCard(if (bills.size == 1) "1 bill" else "${bills.size} bills") {
                bills.forEach { KeyValue(billLabel(it, fines), "$${money(it.outstanding)}") }
                Text("Total USD ${money(total.toString())}", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = CrdcColors.Green)
            }
            ChoicePicker("Pay with", Choices.mobileMoney, method) { method = it }
            Field("Mobile money number", phone, { phone = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Pay USD ${money(total.toString())}", busy = busy, enabled = bills.isNotEmpty() && phone.isNotBlank(), onClick = {
                busy = true
                error = null
                scope.launch {
                    runCatching {
                        val p = sdk.postJson("payments/", buildJsonObject {
                            putJsonArray("bills") { bills.forEach { add(it.id) } }; put("method", method); put("phone", phone)
                        })
                        sdk.store.upsert(Entities.ONLINE_PAYMENTS, p)
                        val ref = AppJson.decodeFromJsonElement(OnlinePayment.serializer(), p).reference
                        ctx.back()
                        ctx.go(CScreen.Payment(ref))
                    }.onFailure { error = it.message ?: "No connection. Try again when you are online." }
                    busy = false
                }
            })
        }
    }
}

// --------------------------------------------------------------- statements
@Composable
fun StatementsScreen(ctx: CCtx) {
    val accounts by ctx.sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    AppScreen("Statements", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (accounts.isEmpty()) item { Empty("No council account linked yet.") }
            items(accounts, key = { it.id }) { a ->
                RowCard(a.name, a.accountNumber, if (a.balance.num() > 0) "$${money(a.balance)}" else "Paid up", a.statusLabel, a.status) {
                    ctx.go(CScreen.Account(a.id))
                }
            }
            item { SecondaryButton("Link another account", { ctx.go(CScreen.LinkAccount) }) }
        }
    }
}

/** Account statement: every bill and payment in date order with the running balance. */
@Composable
fun AccountScreen(ctx: CCtx, id: String) {
    val sdk = ctx.sdk
    val a by sdk.observeOne(Entities.ACCOUNTS, id, ClientAccount.serializer()).collectAsState(initial = null)
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val receipts by sdk.observe(Entities.RECEIPTS, Receipt.serializer()).collectAsState(initial = emptyList())
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    AppScreen("Statement", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val acc = a ?: return@AppScreen Empty("Not found")
        val lines = (bills.filter { it.account == acc.id && it.status != "CANCELLED" }.map { Triple(it.issueDate, it.description, it.amount.num()) } +
            receipts.filter { it.account == acc.id && it.status != "VOIDED" }.map { Triple(it.createdAt.take(10), "Payment ${it.number} – ${it.revenueHeadName}", -it.amount.num()) })
            .sortedBy { it.first }
        val unpaid = bills.filter { it.account == acc.id && it.isDue() }
        ScrollColumn {
            SectionCard(acc.name) {
                KeyValue("Account no.", acc.accountNumber)
                KeyValue("Balance", "USD ${money(acc.balance)}")
                props.filter { it.account == acc.id }.forEach { KeyValue("Stand ${it.standNumber}", it.businessName.ifBlank { it.areaName.ifBlank { it.location } }) }
            }
            if (unpaid.isNotEmpty()) PrimaryButton("Pay $${money(unpaid.sumOf { it.outstanding.num() }.toString())}", onClick = { ctx.go(CScreen.PayBills(unpaid.map { it.id })) })
            SectionCard("Statement") {
                var running = 0.0
                if (lines.isEmpty()) Text("Nothing yet.", color = CrdcColors.Muted)
                lines.forEach { (date, what, amt) ->
                    running += amt
                    RowCard(what, prettyDate(date), (if (amt < 0) "–" else "") + "$${money(kotlin.math.abs(amt).toString())}", "Bal. $${money(running.toString())}",
                        if (amt < 0) "PAID" else "WAITING")
                }
            }
        }
    }
}
