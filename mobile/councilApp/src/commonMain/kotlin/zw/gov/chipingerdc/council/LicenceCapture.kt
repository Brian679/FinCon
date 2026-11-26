package zw.gov.chipingerdc.council

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.ScrollColumn

/** Finance captures a licence application at the counter or in the field (works offline). */
@Composable
fun NewLicenceScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val accounts by ctx.sdk.search(Entities.ACCOUNTS, q, ClientAccount.serializer()).collectAsState(initial = emptyList())
    val props by ctx.sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    var account by remember { mutableStateOf<ClientAccount?>(null) }
    var stand by remember { mutableStateOf<Property?>(null) }
    var type by remember { mutableStateOf("SHOP") }
    var name by remember { mutableStateOf("") }
    var activity by remember { mutableStateOf("") }
    var premises by remember { mutableStateOf("") }
    AppScreen("Capture licence application", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Field("Find account (name, number, phone)", q, { q = it })
            Picker("Council account", accounts.take(30), account, { "${it.accountNumber} – ${it.name}" }, { account = it; stand = null })
            Picker("Stand / shop", props.filter { it.account == account?.id }, stand, { "Stand ${it.standNumber} ${it.areaName} ${it.businessName}" }, {
                stand = it
                if (name.isBlank()) name = it.businessName
                if (premises.isBlank()) premises = "Stand ${it.standNumber}, ${it.areaName.ifBlank { it.location }}"
            })
            ChoicePicker("Licence type", Choices.licenceTypes, type) { type = it }
            Field("Business / trading name", name, { name = it })
            Field("Business activity", activity, { activity = it })
            Field("Premises / stand / trading site", premises, { premises = it })
            PrimaryButton("Save application", enabled = account != null && name.isNotBlank() && premises.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val label = Choices.licenceTypes.first { it.first == type }.second
                val optimistic = buildJsonObject {
                    put("id", id); put("number", "(pending)"); put("licence_type", type); put("licence_type_label", label); put("account", account!!.id)
                    put("business_name", name); put("premises", premises); put("status", "APPLIED"); put("status_label", "Waiting to send")
                    put("updated_at", ctx.sdk.nowIso()); put("local_note", "Saved – sent to the council on sync")
                }
                ctx.sdk.enqueue("licence.apply", "Licence application: $name", Entities.LICENCES, id, optimistic) {
                    put("id", id); put("account", account!!.id); stand?.let { put("property", it.id) }; put("licence_type", type)
                    put("business_name", name); put("business_activity", activity); put("premises", premises)
                }
                ctx.back()
            })
            InfoBox("Shops, food premises and liquor are inspected by the Environmental Health Officer first; then the Treasurer approves and the fee is billed. The licence is issued as soon as the fee is paid.")
        }
    }
}
