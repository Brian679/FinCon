package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.StandBeneficiary
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private fun Ctx.canEditStands() = me.can("accounts.manage", "growth.manage", "land.manage")

/** Every stand, house, shop and farm – search by stand number, place, owner or a beneficiary's name / ID. */
@Composable
fun StandRecordsScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val props by ctx.sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    val people by ctx.sdk.observe(Entities.STAND_BENEFICIARIES, StandBeneficiary.serializer()).collectAsState(initial = emptyList())
    val t = q.trim()
    val list = props.filter { p ->
        t.isBlank() || listOf(p.standNumber, p.location, p.areaName, p.businessName, p.accountName, p.accountNumber).any { it.contains(t, true) } ||
            people.any { it.property == p.id && (it.fullName.contains(t, true) || it.nationalId.contains(t, true)) }
    }.sortedWith(compareBy({ it.areaName.ifBlank { it.location } }, { it.standNumber }))
    AppScreen("Stands, houses & farms", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search stand, place, owner or beneficiary", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("Nothing found.") }
            items(list.take(300), key = { it.id }) { p ->
                val n = people.count { it.property == p.id && it.isActive }
                RowCard("Stand ${p.standNumber} · ${p.areaName.ifBlank { p.location }}",
                    "${p.accountName} · ${p.accountNumber}\n${p.landUseLabel}${p.businessName.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""}",
                    "$n beneficiar${if (n == 1) "y" else "ies"}", null, null) { ctx.go(Screen.StandRecord(p.id)) }
            }
        }
    }
}

@Composable
fun StandRecordScreen(ctx: Ctx, id: String) {
    val prop by ctx.sdk.observeOne(Entities.PROPERTIES, id, Property.serializer()).collectAsState(initial = null)
    val people by ctx.sdk.observe(Entities.STAND_BENEFICIARIES, StandBeneficiary.serializer()).collectAsState(initial = emptyList())
    val accounts by ctx.sdk.observe(Entities.ACCOUNTS, ClientAccount.serializer()).collectAsState(initial = emptyList())
    AppScreen("Stand", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val p = prop ?: return@AppScreen Empty("Not found")
        val owner = accounts.firstOrNull { it.id == p.account }
        val mine = people.filter { it.property == p.id && it.isActive }.sortedBy { it.fullName }
        ScrollColumn {
            SectionCard("Stand ${p.standNumber} · ${p.areaName.ifBlank { p.location }}") {
                KeyValue("Use", p.landUseLabel + (p.hectares?.let { " · $it ha" } ?: ""))
                if (p.businessName.isNotBlank()) KeyValue("Shop / business", p.businessName)
                KeyValue("Owner", "${p.accountName} · ${p.accountNumber}")
                owner?.let { KeyValue("Owner phone", it.phone); KeyValue("Balance", "USD ${money(it.balance)}") }
                p.ward?.let { KeyValue("Ward", it.toString()) }
            }
            SectionCard("Beneficiaries (${mine.size})") {
                if (mine.isEmpty()) Empty("None recorded.")
                mine.forEach { b ->
                    RowCard(b.fullName, listOf(b.relationshipLabel, b.nationalId, b.phone, b.dateOfBirth?.let { "born ${prettyDate(it)}" } ?: "",
                        if (b.addedByName.isNotBlank()) "added by ${b.addedByName}" else "").filter { it.isNotBlank() }.joinToString(" · "),
                        null, if (b.livesHere) "Lives here" else null, if (b.livesHere) "ACTIVE" else null,
                        onClick = if (ctx.canEditStands()) ({ ctx.go(Screen.StandPersonForm(p.id, b.id)) }) else null)
                }
                if (ctx.canEditStands()) PrimaryButton("+ Add a beneficiary", onClick = { ctx.go(Screen.StandPersonForm(p.id, null)) })
            }
            if (owner != null) SecondaryButton("Owner's account", { ctx.go(Screen.AccountDetail(owner.id)) })
        }
    }
}

@Composable
fun StandPersonFormScreen(ctx: Ctx, propertyId: String, id: String?) {
    val existing = remember(id) { id?.let { ctx.sdk.store.get(Entities.STAND_BENEFICIARIES, it, StandBeneficiary.serializer()) } }
    var name by remember { mutableStateOf(existing?.fullName ?: "") }
    var rel by remember { mutableStateOf(existing?.relationship ?: "CHILD") }
    var nid by remember { mutableStateOf(existing?.nationalId ?: "") }
    var dob by remember { mutableStateOf(existing?.dateOfBirth ?: "") }
    var phone by remember { mutableStateOf(existing?.phone ?: "") }
    var livesHere by remember { mutableStateOf(existing?.livesHere ?: true) }
    AppScreen(if (id == null) "Add a beneficiary" else "Beneficiary", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Full name", name, { name = it })
            ChoicePicker("Relationship to the owner", Choices.relationships2, rel) { rel = it }
            Field("National ID", nid, { nid = it.uppercase() })
            Field("Date of birth (YYYY-MM-DD)", dob, { dob = it })
            Field("Phone", phone, { phone = it })
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = livesHere, onCheckedChange = { livesHere = it }); Text("Lives / works at this stand")
            }
            PrimaryButton("Save", enabled = name.isNotBlank() && (dob.isBlank() || Regex("""\d{4}-\d{2}-\d{2}""").matches(dob)), onClick = {
                val bid = id ?: ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", bid); put("property", propertyId); put("full_name", name); put("relationship", rel)
                    put("relationship_label", Choices.relationships2.first { it.first == rel }.second); put("national_id", nid); put("phone", phone)
                    if (dob.isNotBlank()) put("date_of_birth", dob); put("lives_here", livesHere); put("is_active", true); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("stand_beneficiary.save", "Beneficiary: $name", Entities.STAND_BENEFICIARIES, bid, opt) {
                    put("id", bid); put("property", propertyId); put("full_name", name); put("relationship", rel); put("national_id", nid)
                    put("phone", phone); if (dob.isNotBlank()) put("date_of_birth", dob); put("lives_here", livesHere)
                }
                ctx.back()
            })
            if (existing != null) SecondaryButton("Remove", {
                ctx.sdk.enqueue("stand_beneficiary.remove", "Remove beneficiary: ${existing.fullName}", Entities.STAND_BENEFICIARIES, existing.id,
                    buildJsonObject { put("id", existing.id); put("property", propertyId); put("full_name", existing.fullName); put("is_active", false) }) {
                    put("beneficiary", existing.id)
                }
                ctx.back()
            })
        }
    }
}
