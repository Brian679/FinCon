package zw.gov.chipingerdc.client

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
    AppScreen("My stands & shops", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Register a stand / shop", onClick = { ctx.go(CScreen.RegisterStand) })
        ListScreen {
            item {
                InfoBox("Own a house or shop on a council stand, or lease council premises? Register it. If your details match the council register it is " +
                    "linked straight away; otherwise a revenue officer verifies it and you are notified.")
            }
            item { Text("Linked stands", fontSize = 13.sp, color = CrdcColors.Muted) }
            if (props.isEmpty()) item { Empty("No stands linked yet.") }
            items(props, key = { it.id }) { p ->
                RowCard("Stand ${p.standNumber} · ${p.areaName.ifBlank { p.location }}", "${p.businessName.ifBlank { p.landUseLabel }} · account ${p.accountNumber}",
                    "$${money(p.monthlyRates)}/m") { ctx.go(CScreen.Account(p.account)) }
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
    AppScreen("Register a stand / shop", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("I am…", Choices.claimTypes, type) { type = it }
            Field("Stand number", stand, { stand = it })
            Picker("Shopping centre / township / growth point", areas.sortedBy { it.name }, area, { it.name }, { area = it })
            Field("…or type the place if not listed", location, { location = it })
            Field("Shop / business name (if any)", business, { business = it })
            Field("National ID (or company reg. no.)", idNumber, { idNumber = it })
            Field("Phone number", phone, { phone = it })
            Field("Anything that helps us find your stand", notes, { notes = it }, singleLine = false, minLines = 2)
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

@Composable
fun PlansScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.BUILDING_PLANS, BuildingPlan.serializer()).collectAsState(initial = emptyList())
    AppScreen("My building plans", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Submit a building plan", onClick = { ctx.go(CScreen.NewPlan) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No building plans.") }
            items(list, key = { it.id }) { p ->
                SectionCard("${p.developmentTypeLabel} – stand ${p.standNumber}") {
                    Text("${p.reference} · ${p.location}", fontSize = 12.sp, color = CrdcColors.Muted)
                    KeyValue("Status", p.statusLabel)
                    KeyValue("Fee", "$${money(p.fee)} · ${p.billStatus?.ifBlank { null } ?: "no bill yet"}")
                    KeyValue("Decision due", prettyDate(p.dueAt))
                    if (p.decisionNotes.isNotBlank()) KeyValue("Council decision", p.decisionNotes)
                    p.localNote?.let { InfoBox(it) }
                    if (p.bill != null && p.billStatus != "PAID") PrimaryButton("Pay plan fee", onClick = { ctx.go(CScreen.Pay(null, p.bill)) })
                }
            }
        }
    }
}

@Composable
fun NewPlanScreen(ctx: CCtx) {
    val accounts by ctx.sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    var stand by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("RES") }
    var description by remember { mutableStateOf("") }
    var area by remember { mutableStateOf("") }
    AppScreen("Submit building plan", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            if (accounts.isEmpty()) InfoBox("Link your council account first so the plan fee can be billed to it.", CrdcColors.Warning)
            Field("Stand number", stand, { stand = it }); Field("Location", location, { location = it }); Field("Ward", ward, { ward = it }, number = true)
            ChoicePicker("Development", Choices.devTypes, type) { type = it }
            Field("Description (rooms, size, materials)", description, { description = it }, singleLine = false, minLines = 3)
            Field("Floor area (m²)", area, { area = it }, number = true)
            Text("Bring the drawings (3 copies) to the Technical Services office. The decision is made within 30 working days (Client Charter).",
                fontSize = 11.sp, color = CrdcColors.Muted)
            PrimaryButton("Submit", enabled = stand.isNotBlank() && location.isNotBlank() && description.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("stand_number", stand); put("location", location); put("development_type", type)
                    put("status", "SUBMITTED"); put("status_label", "Waiting to send"); put("updated_at", ctx.sdk.nowIso())
                    put("local_note", "Saved on your phone – it will be sent when you are online")
                }
                ctx.sdk.enqueue("plan.create", "Building plan: stand $stand", Entities.BUILDING_PLANS, id, opt) {
                    put("id", id); put("stand_number", stand); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("development_type", type); put("description", description); put("floor_area", area.ifBlank { "0" })
                }
                ctx.back()
            })
        }
    }
}
