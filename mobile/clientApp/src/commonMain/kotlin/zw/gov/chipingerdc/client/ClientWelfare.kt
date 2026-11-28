package zw.gov.chipingerdc.client

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private fun JsonObject.s(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
private fun JsonObject.list(k: String) = (this[k] as? JsonArray)?.map { it.jsonObject } ?: emptyList()

/** Social assistance: the resident's application / beneficiary record and the help received. */
@Composable
fun WelfareScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.BENEFICIARIES, JsonObject.serializer()).collectAsState(initial = emptyList())
    val open = list.any { it.s("status") in listOf("APPLIED", "APPROVED", "") }
    AppScreen("Social assistance", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (!open) item { PrimaryButton("Apply for assistance", onClick = { ctx.go(CScreen.ApplyWelfare) }) }
            if (list.isEmpty()) item { Empty("No application yet.") }
            items(list.sortedByDescending { it.s("created_at") }, key = { it.s("id") }) { b ->
                SectionCard("${b.s("category_label").ifBlank { "Application" }} · ${b.s("reference")}") {
                    Row { StatusChip(b.s("status_label").ifBlank { "Waiting to send" },
                        when (b.s("status")) { "APPLIED" -> "PENDING"; "APPROVED" -> "ACTIVE"; "REJECTED" -> "REJECTED"; else -> "WAITING" }) }
                    if (b.s("need_label").isNotBlank()) KeyValue("Help asked for", b.s("need_label"))
                    KeyValue("Household", "${b.s("household_size")} people, ${b.s("children").ifBlank { "0" }} children · ${b.s("village")}")
                    if (b.s("assessment_note").isNotBlank()) KeyValue("Council", b.s("assessment_note"))
                    val help = b.list("assistance")
                    if (help.isNotEmpty()) {
                        KeyValue("Assistance received", "USD ${money(b.s("assistance_total"))}")
                        help.forEach { a ->
                            RowCard(a.s("kind"), "${prettyDate(a.s("date"))} · ${a.s("description")}" +
                                (a.s("programme").takeIf { it.isNotBlank() }?.let { "\n$it" } ?: ""), "$${money(a.s("value"))}", null, null)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ApplyWelfareScreen(ctx: CCtx) {
    var category by remember { mutableStateOf("ELDERLY") }
    var need by remember { mutableStateOf("FOOD") }
    var village by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var size by remember { mutableStateOf("") }
    var children by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    AppScreen("Apply for assistance", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("My household", Choices.welfareCategories, category) { category = it }
            ChoicePicker("Help needed", Choices.welfareNeeds, need) { need = it }
            Field("Village / street", village, { village = it })
            Field("Ward", ward, { ward = it }, number = true)
            Field("People in the household", size, { size = it }, number = true)
            Field("Children under 18", children, { children = it }, number = true)
            Field("Why we need help", reason, { reason = it }, singleLine = false, minLines = 3)
            PrimaryButton("Send application", enabled = village.isNotBlank() && reason.isNotBlank() && (size.toIntOrNull() ?: 0) > 0, onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("category", category)
                    put("category_label", Choices.welfareCategories.first { it.first == category }.second)
                    put("need_label", Choices.welfareNeeds.first { it.first == need }.second); put("village", village); put("household_size", size)
                    put("children", children.ifBlank { "0" }); put("status", "APPLIED"); put("status_label", "Waiting to send")
                    put("created_at", ctx.sdk.nowIso()); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("assistance.apply", "Application for assistance", Entities.BENEFICIARIES, id, opt) {
                    put("id", id); put("category", category); put("need", need); put("village", village); ward.toIntOrNull()?.let { put("ward", it) }
                    put("household_size", size.toIntOrNull() ?: 1); put("children", children.toIntOrNull() ?: 0); put("reason", reason)
                }
                ctx.back()
            })
        }
    }
}
