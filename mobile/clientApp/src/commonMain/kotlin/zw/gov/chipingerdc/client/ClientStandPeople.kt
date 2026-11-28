package zw.gov.chipingerdc.client

import androidx.compose.foundation.layout.Row
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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.StandBeneficiary
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.prettyDate

/** The people on one stand / house / shop / farm. */
@Composable
fun StandPeopleScreen(ctx: CCtx, propertyId: String, title: String) {
    val all by ctx.sdk.observe(Entities.STAND_BENEFICIARIES, StandBeneficiary.serializer()).collectAsState(initial = emptyList())
    val list = all.filter { it.property == propertyId && it.isActive }.sortedBy { it.fullName }
    AppScreen("Beneficiaries", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { zw.gov.chipingerdc.shared.ui.Caption(title) }
            item { PrimaryButton("+ Add a beneficiary", onClick = { ctx.go(CScreen.StandPerson(propertyId, null)) }) }
            if (list.isEmpty()) item { Empty("No beneficiaries yet.") }
            items(list, key = { it.id }) { b ->
                RowCard(b.fullName, listOf(b.relationshipLabel, b.nationalId, b.phone, b.dateOfBirth?.let { "born ${prettyDate(it)}" } ?: "")
                    .filter { it.isNotBlank() }.joinToString(" · "), null, if (b.livesHere) "Lives here" else null, if (b.livesHere) "ACTIVE" else null) {
                    ctx.go(CScreen.StandPerson(propertyId, b.id))
                }
            }
        }
    }
}

@Composable
fun StandPersonScreen(ctx: CCtx, propertyId: String, id: String?) {
    val existing = remember(id) { id?.let { ctx.sdk.store.get(Entities.STAND_BENEFICIARIES, it, StandBeneficiary.serializer()) } }
    var name by remember { mutableStateOf(existing?.fullName ?: "") }
    var rel by remember { mutableStateOf(existing?.relationship ?: "CHILD") }
    var nid by remember { mutableStateOf(existing?.nationalId ?: "") }
    var dob by remember { mutableStateOf(existing?.dateOfBirth ?: "") }
    var phone by remember { mutableStateOf(existing?.phone ?: "") }
    var livesHere by remember { mutableStateOf(existing?.livesHere ?: true) }
    var notes by remember { mutableStateOf(existing?.notes ?: "") }
    val dobOk = dob.isBlank() || Regex("""\d{4}-\d{2}-\d{2}""").matches(dob)
    AppScreen(if (id == null) "Add a beneficiary" else "Beneficiary", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Full name", name, { name = it })
            ChoicePicker("Relationship", Choices.relationships2, rel) { rel = it }
            Field("National ID", nid, { nid = it.uppercase() })
            Field("Date of birth (YYYY-MM-DD)", dob, { dob = it })
            Field("Phone", phone, { phone = it })
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = livesHere, onCheckedChange = { livesHere = it })
                Text("Lives / works at this stand")
            }
            Field("Notes", notes, { notes = it })
            PrimaryButton("Save", enabled = name.isNotBlank() && dobOk, onClick = {
                val bid = id ?: ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", bid); put("property", propertyId); put("full_name", name); put("relationship", rel)
                    put("relationship_label", Choices.relationships2.first { it.first == rel }.second); put("national_id", nid); put("phone", phone)
                    if (dob.isNotBlank()) put("date_of_birth", dob); put("lives_here", livesHere); put("notes", notes); put("is_active", true)
                    put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("stand_beneficiary.save", "Beneficiary: $name", Entities.STAND_BENEFICIARIES, bid, opt) {
                    put("id", bid); put("property", propertyId); put("full_name", name); put("relationship", rel); put("national_id", nid)
                    put("phone", phone); if (dob.isNotBlank()) put("date_of_birth", dob); put("lives_here", livesHere); put("notes", notes)
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
            if (!dobOk) Text("Date as YYYY-MM-DD", color = CrdcColors.Danger)
        }
    }
}
