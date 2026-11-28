package zw.gov.chipingerdc.client

import kotlinx.datetime.toLocalDateTime
import androidx.compose.ui.text.font.FontWeight
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.MessageKind
import zw.gov.chipingerdc.shared.ui.Message
import zw.gov.chipingerdc.shared.model.licenceWords
import zw.gov.chipingerdc.shared.model.shopStatus
import zw.gov.chipingerdc.shared.model.ShopStatus
import zw.gov.chipingerdc.shared.model.Licence
import zw.gov.chipingerdc.shared.model.Bill
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.AccountClaim
import zw.gov.chipingerdc.shared.model.BuildingPlan
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Lease
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.TradingArea
import zw.gov.chipingerdc.shared.model.Tenancy
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

/** Stands / shops linked to the client, plus their registration requests and leases. */
@Composable
fun MyStandsScreen(ctx: CCtx) {
    val sdk = ctx.sdk
    val props by sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    val claims by sdk.observe(Entities.CLAIMS, AccountClaim.serializer()).collectAsState(initial = emptyList())
    val leases by sdk.observe(Entities.LEASES, Lease.serializer()).collectAsState(initial = emptyList())
    val bills by sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    val licences by sdk.observe(Entities.LICENCES, Licence.serializer()).collectAsState(initial = emptyList())
    val rented by sdk.observe(Entities.TENANCIES, Tenancy.serializer()).collectAsState(initial = emptyList())
    val people by sdk.observe(Entities.STAND_BENEFICIARIES, zw.gov.chipingerdc.shared.model.StandBeneficiary.serializer()).collectAsState(initial = emptyList())
    val today = kotlinx.datetime.Clock.System.now().toLocalDateTime(kotlinx.datetime.TimeZone.of("Africa/Harare")).date.toString()
    AppScreen("My stands, shops & farms", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Add a stand / shop / farm", onClick = { ctx.go(CScreen.RegisterStand) })
        ListScreen {
            item { Text("Linked stands", fontSize = 13.sp, color = CrdcColors.Muted) }
            if (props.isEmpty()) item { Empty("No stands linked yet.") }
            items(props, key = { it.id }) { p -> ShopCard(ctx, shopStatus(p, bills, licences, leases, today), bills, people.count { it.property == p.id && it.isActive }) }
            if (rented.isNotEmpty()) {
                item { Text("Places I rent", fontSize = 13.sp, color = CrdcColors.Muted) }
                items(rented, key = { it.id }) { t ->
                    RowCard("Stand ${t.standNumber} · ${t.areaName.ifBlank { t.location }}", "${t.businessName.ifBlank { t.landUse }}\nMy account ${t.tenantAccountNumber}" +
                        (t.startDate?.let { " · since ${prettyDate(it)}" } ?: "") + "\nBeneficiaries: ${people.count { it.property == t.property && it.isActive }}",
                        null, if (t.isActive) "Renting" else "Ended", if (t.isActive) "ACTIVE" else "ENDED") {
                        ctx.go(CScreen.StandPeople(t.property, "Stand ${t.standNumber} · ${t.areaName.ifBlank { t.location }}"))
                    }
                }
            }
            if (leases.isNotEmpty()) {
                item { Text("Leases", fontSize = 13.sp, color = CrdcColors.Muted) }
                items(leases, key = { it.id }) { l ->
                    RowCard(l.premisesName, "${l.number} · ${l.purpose}\nUntil ${prettyDate(l.endDate)}", "$${money(l.monthlyRent)}/m", l.statusLabel, l.status)
                }
            }
            item { Text("My registration requests", fontSize = 13.sp, color = CrdcColors.Muted) }
            if (claims.isEmpty()) item { Empty("No requests.") }
            items(claims, key = { it.id }) { c ->
                RowCard("Stand ${c.standNumber} · ${c.areaName.ifBlank { c.location }}", "${c.reference} · ${c.businessName}\n${c.decisionNote}", null,
                    c.statusLabel, c.status, c.localNote)
            }
        }
    }
}

@Composable
fun RegisterStandScreen(ctx: CCtx) {
    val areas by ctx.sdk.observe(Entities.TRADING_AREAS, TradingArea.serializer()).collectAsState(initial = emptyList())
    var type by remember { mutableStateOf("OWNER") }
    var stand by remember { mutableStateOf("") }
    var area by remember { mutableStateOf<TradingArea?>(null) }
    var location by remember { mutableStateOf("") }
    var business by remember { mutableStateOf("") }
    var idNumber by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf(ctx.me.phone) }
    var notes by remember { mutableStateOf("") }
    AppScreen("Add a stand / shop / farm", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("I am…", Choices.claimTypes, type) { type = it }
            Field("Stand number", stand, { stand = it })
            Picker("Shopping centre / township / growth point", areas.sortedBy { it.name }, area, { it.name }, { area = it })
            Field("…or type the place if not listed", location, { location = it })
            Field("Shop / business name (if any)", business, { business = it })
            Field("National ID (or company reg. no.)", idNumber, { idNumber = it })
            Field("Phone number", phone, { phone = it })
            Field("Notes", notes, { notes = it }, singleLine = false, minLines = 2)
            PrimaryButton("Send", enabled = stand.isNotBlank() && (area != null || location.isNotBlank()) && phone.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("stand_number", stand); put("area_name", area?.name ?: location)
                    put("business_name", business); put("status", "PENDING"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                    put("local_note", "Saved on your phone – it will be sent when you are online")
                }
                ctx.sdk.enqueue("claim.create", "Stand registration: $stand", Entities.CLAIMS, id, opt) {
                    put("id", id); put("claim_type", type); put("stand_number", stand); area?.let { put("area", it.id) }; put("location", location)
                    put("business_name", business); put("id_number", idNumber); put("phone", phone); put("notes", notes)
                }
                // linked stands, bills and licences arrive with the next sync once approved
                listOf(Entities.ACCOUNTS, Entities.PROPERTIES, Entities.BILLS, Entities.RECEIPTS, Entities.LICENCES).forEach { ctx.sdk.store.resetCursor(it) }
                ctx.back()
            })
        }
    }
}




/** One shop / stand with its paid-up position – updated as soon as the council records a payment. */
@Composable
fun ShopCard(ctx: CCtx, r: ShopStatus, bills: List<Bill>, people: Int = 0) {
    val p = r.property
    SectionCard("Stand ${p.standNumber} · ${p.areaName.ifBlank { p.location }}") {
        Text(p.businessName.ifBlank { p.landUseLabel }, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        Text("Account ${p.accountNumber}", fontSize = 12.sp, color = CrdcColors.Muted)
        if (r.ok) Message("Paid up – nothing owing" + (licenceWords[r.licence]?.takeIf { it.isNotBlank() }?.let { ". $it" } ?: ""), MessageKind.SUCCESS)
        else {
            if (r.total > 0) Message("Balance remaining: USD ${money(r.total.toString())}", MessageKind.ERROR)
            if (r.rates > 0) KeyValue("Rates", money(r.rates.toString()))
            if (r.levies > 0) KeyValue("Levies", money(r.levies.toString()))
            if (r.rent > 0) KeyValue("Rent / lease", money(r.rent.toString()))
            if (r.other > 0) KeyValue("Other (licence fee …)", money(r.other.toString()))
            licenceWords[r.licence]?.takeIf { it.isNotBlank() }?.let { KeyValue("Licence", it) }
            val due = bills.filter { it.property == p.id && it.status in listOf("UNPAID", "PART") }.map { it.id }
            if (r.total > 0) PrimaryButton("Pay USD ${money(r.total.toString())}", onClick = { ctx.go(CScreen.PayBills(due)) })
            if (r.licence in listOf("NONE", "EXPIRED")) SecondaryButton("Apply / renew shop licence", { ctx.go(CScreen.ApplyLicence) })
        }
        SecondaryButton("Beneficiaries ($people)", { ctx.go(CScreen.StandPeople(p.id, "Stand ${p.standNumber} · ${p.areaName.ifBlank { p.location }}")) })
    }
}
