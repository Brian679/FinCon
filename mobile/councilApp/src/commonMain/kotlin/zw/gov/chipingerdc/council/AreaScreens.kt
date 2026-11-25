package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlinx.serialization.json.add
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import zw.gov.chipingerdc.shared.model.AccountClaim
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Lease
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.TradingArea
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
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

/** Paid / unpaid position of one stand or shop, computed from the phone's database. */
data class ShopStatus(
    val property: Property, val rates: Double, val levies: Double, val rent: Double, val other: Double,
    val licence: String, val lease: Lease?,
) {
    val total get() = rates + levies + rent + other
    val ok get() = total <= 0.005 && licence in listOf("VALID", "N/A")
}

fun shopStatus(p: Property, bills: List<Bill>, licences: List<Licence>, leases: List<Lease>, today: String): ShopStatus {
    val open = bills.filter { it.property == p.id && it.status in listOf("UNPAID", "PART") }
    fun sum(cat: (String) -> Boolean) = open.filter { cat(it.revenueHeadCategory) }.sumOf { it.outstanding.toDoubleOrNull() ?: 0.0 }
    val lic = licences.filter { it.property == p.id }.maxByOrNull { it.createdAt }
    val needs = p.landUse in listOf("COM", "IND") || p.businessName.isNotBlank()
    val licence = when {
        lic == null -> if (needs) "NONE" else "N/A"
        lic.status == "ISSUED" && (lic.expiryDate ?: "") >= today -> "VALID"
        lic.status == "APPROVED" -> "UNPAID"
        lic.status in listOf("APPLIED", "INSPECTION", "INSPECTED") -> "PROCESSING"
        lic.status in listOf("EXPIRED", "ISSUED") -> "EXPIRED"
        else -> "NONE"
    }
    return ShopStatus(p, sum { it == "RATES" }, sum { it == "LEVY" }, sum { it == "RENT" }, sum { it !in listOf("RATES", "LEVY", "RENT") },
        licence, leases.firstOrNull { it.premises == p.id && it.status == "ACTIVE" })
}

private val licenceText = mapOf("VALID" to "Licence valid", "UNPAID" to "Licence fee unpaid", "PROCESSING" to "Licence processing",
    "EXPIRED" to "Licence expired", "NONE" to "No licence", "N/A" to "")

@Composable
fun AreasScreen(ctx: Ctx) {
    val areas by ctx.sdk.observe(Entities.TRADING_AREAS, TradingArea.serializer()).collectAsState(initial = emptyList())
    val props by ctx.sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    AppScreen("Shops & stands by area", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (areas.isEmpty()) item { Empty("No trading areas synced.") }
            items(areas.sortedBy { it.name }, key = { it.id }) { a ->
                RowCard(a.name, "${a.kindLabel} · Ward ${a.ward ?: "-"}", "${props.count { it.area == a.id }} stands") { ctx.go(Screen.AreaBoard(a.id)) }
            }
        }
    }
}

@Composable
fun AreaBoardScreen(ctx: Ctx, areaId: String) {
    val sdk = ctx.sdk
    val area by sdk.observeOne(Entities.TRADING_AREAS, areaId, TradingArea.serializer()).collectAsState(initial = null)
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val licences by sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    val leases by sdk.observe(Entities.LEASES, Lease.serializer()).collectAsState(initial = emptyList())
    val today = Clock.System.now().toLocalDateTime(TimeZone.of("Africa/Harare")).date.toString()
    val rows = props.filter { it.area == areaId && it.isActive }.sortedBy { it.standNumber }.map { shopStatus(it, bills, licences, leases, today) }
    var show by remember { mutableStateOf("ALL") }
    val selected = remember { mutableStateListOf<String>() }
    var extra by remember { mutableStateOf("") }
    var sentNote by remember { mutableStateOf<String?>(null) }
    val shown = when (show) {
        "OWING" -> rows.filter { !it.ok }
        "PAID" -> rows.filter { it.ok }
        "UNREG" -> rows.filter { !it.property.registered }
        else -> rows
    }
    AppScreen(area?.name ?: "Area", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Kpi("Paid up", rows.count { it.ok }.toString(), "of ${rows.size} stands", CrdcColors.Success, Modifier.weight(1f))
                    Kpi("Owing", rows.count { !it.ok }.toString(), "$${money(rows.sumOf { it.total }.toString())}", CrdcColors.Danger, Modifier.weight(1f))
                    Kpi("Not on app", rows.count { !it.property.registered }.toString(), null, CrdcColors.Blue, Modifier.weight(1f))
                }
            }
            item { ChoicePicker("Show", listOf("ALL" to "All stands", "OWING" to "Owing", "PAID" to "Paid up", "UNREG" to "Not registered on app"), show) { show = it } }
            if (shown.isEmpty()) item { Empty("No stands.") }
            items(shown, key = { it.property.id }) { r ->
                val p = r.property
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (ctx.me.can("reminders.send")) Checkbox(checked = p.id in selected, onCheckedChange = { if (it) selected.add(p.id) else selected.remove(p.id) })
                    Row(Modifier.weight(1f)) {
                        RowCard(
                            "${p.standNumber} · ${p.businessName.ifBlank { p.accountName }}",
                            buildString {
                                append("${p.accountName} (${p.accountNumber}) ${p.accountPhone}")
                                if (r.rates > 0) append("\nRates $${money(r.rates.toString())}")
                                if (r.levies > 0) append(" · Levies $${money(r.levies.toString())}")
                                if (r.rent > 0) append(" · Rent $${money(r.rent.toString())}")
                                licenceText[r.licence]?.takeIf { it.isNotBlank() }?.let { append("\n$it") }
                                if (!p.registered) append(" · not on app")
                            },
                            if (r.ok) null else "$${money(r.total.toString())}",
                            if (r.ok) "PAID UP" else "OWING", if (r.ok) "PAID" else "URGENT",
                        ) { ctx.go(Screen.AccountDetail(p.account)) }
                    }
                }
            }
            if (ctx.me.can("reminders.send")) item {
                SectionCard("Send payment reminders") {
                    Text(if (selected.isEmpty()) "No stands ticked – reminders go to every stand in this area that owes money or has no valid licence."
                    else "${selected.size} stand(s) ticked.", fontSize = 12.sp, color = CrdcColors.Muted)
                    Field("Extra line (optional)", extra, { extra = it })
                    sentNote?.let { InfoBox(it, CrdcColors.Success) }
                    PrimaryButton("Send by SMS & app notification", color = CrdcColors.Warning, onClick = {
                        sdk.enqueue("reminders.send", "Reminders – ${area?.name ?: ""}") {
                            if (selected.isEmpty()) put("area", areaId) else putJsonArray("properties") { selected.forEach { add(it) } }
                            put("extra", extra); put("campaign", "Reminder – ${area?.name ?: ""} (mobile)")
                        }
                        sentNote = "Queued – the council server sends the SMS and notifications on the next sync. Owners not on the app are invited to register."
                        selected.clear()
                    })
                }
            }
        }
    }
}

@Composable
fun ClaimsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.CLAIMS, AccountClaim.serializer()).collectAsState(initial = emptyList())
    AppScreen("Stand registration requests", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No requests.") }
            items(list.sortedByDescending { it.status == "PENDING" }, key = { it.id }) { c ->
                RowCard("Stand ${c.standNumber} · ${c.areaName.ifBlank { c.location }}", "${c.reference} · ${c.userName} · ${c.businessName}\n" +
                    (if (c.matched.isNotBlank()) "Matches register: ${c.matched}" else "Not found in register"),
                    null, c.statusLabel, c.status, c.localNote) { ctx.go(Screen.ClaimDetail(c.id)) }
            }
        }
    }
}

@Composable
fun ClaimDetailScreen(ctx: Ctx, id: String) {
    val c by ctx.sdk.observeOne(Entities.CLAIMS, id, AccountClaim.serializer()).collectAsState(initial = null)
    AppScreen("Stand claim", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val cl = c ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(cl.reference) {
                KeyValue("Client", cl.userName)
                KeyValue("Claim", cl.claimTypeLabel)
                KeyValue("Stand", "${cl.standNumber} · ${cl.areaName.ifBlank { cl.location }}")
                KeyValue("Business", cl.businessName)
                KeyValue("ID / phone given", "${cl.idNumber} · ${cl.phone}")
                KeyValue("Notes", cl.notes)
                KeyValue("Register match", cl.matched.ifBlank { "Not found in register" })
                KeyValue("Decision", cl.decisionNote)
                Row { StatusChip(cl.statusLabel, cl.status) }
                cl.localNote?.let { InfoBox(it) }
            }
            if (cl.status == "PENDING" && cl.localNote == null && ctx.me.can("claims.review")) {
                val buttons = buildList {
                    if (cl.matchedProperty != null) add("link" to "Approve – link to matched stand owner")
                    else add("create" to "Approve – register new account & stand")
                    add("reject" to "Reject")
                }
                ActionPanel("Verify & decide", listOf(FieldSpec("monthly_rates", "Monthly rates for a new stand (USD)", "number"),
                    FieldSpec("note", "Note to client", "multiline")), buttons,
                    note = "Check the client's ID and agreement of sale / lease before approving.") { action, v ->
                    ctx.sdk.markPending(Entities.CLAIMS, cl.id, "Decision queued")
                    ctx.sdk.enqueue("claim.decide", "Stand claim ${cl.reference}", Entities.CLAIMS, cl.id) {
                        put("claim", cl.id); put("approve", action != "reject"); put("create_account", action == "create")
                        put("note", v["note"] ?: ""); v["monthly_rates"]?.takeIf { it.isNotBlank() }?.let { put("monthly_rates", it) }
                    }
                }
            }
        }
    }
}

@Composable
fun LeasesScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.LEASES, Lease.serializer()).collectAsState(initial = emptyList())
    AppScreen("Leases of council premises", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No leases.") }
            items(list, key = { it.id }) { l ->
                RowCard(l.premisesName, "${l.number} · ${l.lesseeName} · ${l.purpose}\n${prettyDate(l.startDate)} – ${prettyDate(l.endDate)}",
                    "$${money(l.monthlyRent)}/m", l.statusLabel, l.status)
            }
        }
    }
}
