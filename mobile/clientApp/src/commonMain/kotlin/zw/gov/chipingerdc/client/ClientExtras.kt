package zw.gov.chipingerdc.client

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.EmptyState
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private fun JsonObject.s(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
private fun JsonObject.list(k: String) = (this[k] as? JsonArray)?.map { it.jsonObject } ?: emptyList()

// ------------------------------------------------------------------- fines
@Composable
fun FinesScreen(ctx: CCtx) {
    val fines by ctx.sdk.observe(Entities.FINES, JsonObject.serializer()).collectAsState(initial = emptyList())
    AppScreen("My fines", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("Find a fine by its number", onClick = { ctx.go(CScreen.FindFine) })
        ListScreen {
            if (fines.isEmpty()) item {
                EmptyState("No fines on your accounts.", "Got a fine slip or SMS from a council officer? Find it with the fine number and pay it here.",
                    "Find my fine") { ctx.go(CScreen.FindFine) }
            }
            items(fines.sortedByDescending { it.s("date") }, key = { it.s("id") }) { f ->
                SectionCard("${f.s("reference")} – ${f.s("offence_name").substringBefore(" (")}") {
                    KeyValue("Where", f.s("location")); KeyValue("Date", prettyDate(f.s("date")))
                    KeyValue("Amount", "USD ${money(f.s("amount"))}")
                    Row { StatusChip(f.s("status_label"), when (f.s("status")) { "ISSUED" -> "UNPAID"; "COURT" -> "URGENT"; else -> f.s("status") }) }
                    if (f.s("status") == "ISSUED" && f.s("bill").isNotBlank())
                        PrimaryButton("Pay fine $${money(f.s("amount"))}", onClick = { ctx.go(CScreen.Pay(f.s("account"), f.s("bill"))) })
                }
            }
        }
    }
}

@Composable
fun FindFineScreen(ctx: CCtx) {
    val scope = rememberCoroutineScope()
    var ref by remember { mutableStateOf("") }
    var key by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Find my fine", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            InfoBox("Enter the fine number from the fine slip or SMS (e.g. FIN-2026-00004) and the phone number or National ID given to the officer.")
            Field("Fine number", ref, { ref = it.uppercase() })
            Field("Phone number or National ID", key, { key = it })
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Find fine", busy = busy, enabled = ref.isNotBlank() && key.isNotBlank(), onClick = {
                busy = true; error = null
                scope.launch {
                    runCatching {
                        val r = ctx.sdk.postJson("fines/claim/", buildJsonObject { put("reference", ref.trim()); put("id_or_phone", key.trim()) })
                        (r["account"] as? JsonObject)?.let { ctx.sdk.store.upsert(Entities.ACCOUNTS, it) }
                        (r["fine"] as? JsonObject)?.let { ctx.sdk.store.upsert(Entities.FINES, it) }
                        listOf(Entities.ACCOUNTS, Entities.BILLS, Entities.FINES, Entities.RECEIPTS).forEach { ctx.sdk.store.resetCursor(it) }
                        ctx.sdk.sync.sync()
                        ctx.back()
                    }.onFailure { error = it.message ?: "Could not find the fine – are you online?" }
                    busy = false
                }
            })
        }
    }
}

// ---------------------------------------------------------- resource permits
/** Same default fees as the council (the deciding officer may adjust them). */
private val TARIFF = listOf(
    Triple("SAND", "Sand extraction", "cubic metres" to 3.0), Triple("GRAVEL", "Gravel / quarry stone", "cubic metres" to 4.0),
    Triple("CLAY", "Clay / brick moulding", "cubic metres" to 2.0), Triple("FIREWOOD", "Firewood", "cords / stacks" to 5.0),
    Triple("THATCH", "Thatch grass & reeds", "bundles" to 0.5), Triple("TIMBER", "Timber harvesting", "cubic metres" to 12.0),
    Triple("MINING", "Small-scale mining", "months" to 75.0),
)

@Composable
fun PermitsScreen(ctx: CCtx) {
    val permits by ctx.sdk.observe(Entities.RESOURCE_PERMITS, JsonObject.serializer()).collectAsState(initial = emptyList())
    AppScreen("Sand & natural resource permits", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Apply for a permit", onClick = { ctx.go(CScreen.ApplyPermit) })
        ListScreen {
            if (permits.isEmpty()) item {
                EmptyState("No permits yet.", "Apply for a sand, gravel, clay, firewood or thatch permit, pay in the app and show the permit at the collection point.",
                    "Apply for a permit") { ctx.go(CScreen.ApplyPermit) }
            }
            items(permits.sortedByDescending { it.s("created_at") }, key = { it.s("id") }) { p ->
                val active = p.s("status") == "ACTIVE"
                SectionCard("${p.s("permit_type_label")} – ${p.s("reference")}") {
                    if (active) {
                        KeyValue("Permit number", p.s("reference"))
                        KeyValue("Valid until", prettyDate(p.s("valid_to")))
                        Text("Show the permit number to the council officer at the collection point.", fontSize = 12.sp, color = CrdcColors.Muted)
                    }
                    KeyValue("Site", "${p.s("location")}${p.s("ward").takeIf { it.isNotBlank() }?.let { ", ward $it" } ?: ""}")
                    KeyValue("Allowed", "${money(p.s("quantity_allowed"))} ${p.s("unit_label")}")
                    if (active) KeyValue("Taken / left", "${money(p.s("quantity_extracted"))} / ${money(p.s("quantity_left"))} ${p.s("unit_label")}")
                    KeyValue("Fee", "USD ${money(p.s("fee"))}")
                    if (p.s("decision_note").isNotBlank()) KeyValue("Council note", p.s("decision_note"))
                    Row { StatusChip(p.s("status_label").ifBlank { "Waiting to send" }, p.s("status")) }
                    p.s("local_note").takeIf { it.isNotBlank() }?.let { InfoBox(it) }
                    when (p.s("status")) {
                        "APPLIED" -> Text("The Environmental Management Officer will check the site and approve – you will get a notification to pay.",
                            fontSize = 12.sp, color = CrdcColors.Muted)
                        "APPROVED" -> if (p.s("bill").isNotBlank())
                            PrimaryButton("Pay $${money(p.s("fee"))} to get the permit", onClick = { ctx.go(CScreen.Pay(p.s("holder"), p.s("bill"))) })
                    }
                }
            }
        }
    }
}

@Composable
fun ApplyPermitScreen(ctx: CCtx) {
    val accounts by ctx.sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    var type by remember { mutableStateOf("SAND") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var qty by remember { mutableStateOf("") }
    var days by remember { mutableStateOf("30") }
    var purpose by remember { mutableStateOf("") }
    val t = TARIFF.first { it.first == type }
    val estimate = (qty.toDoubleOrNull() ?: 0.0) * t.third.second
    AppScreen("Apply for a permit", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("What do you want to collect?", TARIFF.map { it.first to it.second }, type) { type = it }
            Field("Where (river, pit, forest, village) *", location, { location = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("How much (${t.third.first}) *", qty, { qty = it }, number = true)
            Field("For how many days", days, { days = it }, number = true)
            Field("What is it for?", purpose, { purpose = it }, singleLine = false, minLines = 2)
            SectionCard("Estimated fee") {
                KeyValue("Rate", "USD ${money(t.third.second.toString())} per ${t.third.first.removeSuffix("s")}")
                Text("USD ${money(estimate.toString())}", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = CrdcColors.Green)
                Text("The officer confirms the fee when approving. You pay in the app (EcoCash / OneMoney / InnBucks) and the permit is issued at once.",
                    fontSize = 12.sp, color = CrdcColors.Muted)
            }
            if (accounts.isEmpty()) InfoBox("No council account yet – one will be opened in your name so you can pay for the permit.")
            PrimaryButton("Send application", enabled = location.isNotBlank() && (qty.toDoubleOrNull() ?: 0.0) > 0, onClick = {
                val id = ctx.sdk.newId()
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("permit_type", type); put("permit_type_label", t.second); put("location", location)
                    put("quantity_allowed", qty); put("unit_label", t.third.first); put("fee", estimate.toString()); put("status", "APPLIED")
                    put("status_label", "Waiting to send"); put("created_at", ctx.sdk.nowIso()); put("updated_at", ctx.sdk.nowIso())
                    put("local_note", "Saved on your phone – sent to the council as soon as you are online")
                }
                ctx.sdk.enqueue("permit.apply", "Permit: ${t.second} at $location", Entities.RESOURCE_PERMITS, id, optimistic) {
                    put("id", id); put("permit_type", type); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("quantity", qty); put("days", days.toIntOrNull() ?: 30); put("purpose", purpose)
                    accounts.firstOrNull()?.let { put("holder", it.id) }
                }
                ctx.back()
            })
        }
    }
}

// ------------------------------------------------------------------ notices
/** One notice as a Django admin result row. */
@Composable
fun NoticeRow(n: JsonObject) {
    RowCard(n.s("title"), "${n.s("body")}\n${n.s("category_label")} · ${n.s("ward").takeIf { it.isNotBlank() }?.let { "ward $it" } ?: "whole district"} · ${prettyDate(n.s("publish_from"))}",
        null, null, null, null)
}

@Composable
fun NoticesScreen(ctx: CCtx) {
    val notices by ctx.sdk.observe(Entities.PUBLIC_NOTICES, JsonObject.serializer()).collectAsState(initial = emptyList())
    AppScreen("Council notices", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (notices.isEmpty()) item { EmptyState("No notices right now.", "Water cuts, meetings, deadlines and health alerts from the council appear here.") }
            items(notices.sortedByDescending { it.s("publish_from") }, key = { it.s("id") }) { n -> NoticeRow(n) }
        }
    }
}
