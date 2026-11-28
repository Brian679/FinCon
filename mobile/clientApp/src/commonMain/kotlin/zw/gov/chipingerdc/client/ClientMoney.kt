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

// ----------------------------------------------------------------- my bills

// -------------------------------------------------------------- pay bills
/** Pays one bill, a few, or everything – the resident ticks the bills and may pay less than the total (what they have
 *  today); the money goes to the oldest bills first. One mobile-money prompt, a receipt for every bill paid. */
@Composable
fun PayBillsScreen(ctx: CCtx, ids: List<String>) {
    val sdk = ctx.sdk
    val scope = rememberCoroutineScope()
    val all by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val fines by sdk.observe(Entities.FINES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val bills = all.filter { it.id in ids && it.isDue() }.sortedBy { it.dueDate }
    var unticked by remember { mutableStateOf(setOf<String>()) }
    val chosen = bills.filter { it.id !in unticked }
    val total = chosen.sumOf { it.outstanding.num() }
    var amount by remember { mutableStateOf("") }
    var edited by remember { mutableStateOf(false) }
    if (!edited) amount = money(total.toString()).replace(",", "")
    val pay = amount.replace(",", "").toDoubleOrNull() ?: 0.0
    var method by remember { mutableStateOf("ECOCASH") }
    var phone by remember { mutableStateOf(ctx.me.phone) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Pay", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            SectionCard(if (bills.size == 1) "1 bill" else "${bills.size} bills") {
                bills.forEach { b ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        if (bills.size > 1) androidx.compose.material3.Checkbox(checked = b.id !in unticked, onCheckedChange = { on ->
                            unticked = if (on) unticked - b.id else unticked + b.id
                            edited = false
                        })
                        androidx.compose.foundation.layout.Column(Modifier.weight(1f)) {
                            Text(billLabel(b, fines), fontSize = 14.sp)
                            val where = b.description.substringAfter(" – ", "").ifBlank { b.description.substringAfter(" - ", "") }
                            if (where.isNotBlank()) Text(where, fontSize = 12.sp, color = CrdcColors.Muted)
                        }
                        Text("$${money(b.outstanding)}", fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            Field("Amount to pay (USD)", amount, { amount = it; edited = true }, number = true)
            ChoicePicker("Pay with", Choices.mobileMoney, method) { method = it }
            Field("Mobile money number", phone, { phone = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Pay USD ${money(pay.toString())}", busy = busy,
                enabled = chosen.isNotEmpty() && phone.isNotBlank() && pay >= 1 && pay <= total + 0.001, onClick = {
                busy = true
                error = null
                scope.launch {
                    runCatching {
                        val p = sdk.postJson("payments/", buildJsonObject {
                            putJsonArray("bills") { chosen.forEach { add(it.id) } }; put("amount", amount.replace(",", ""))
                            put("method", method); put("phone", phone)
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
            item { SecondaryButton("Add an existing account", { ctx.go(CScreen.LinkAccount) }) }
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
