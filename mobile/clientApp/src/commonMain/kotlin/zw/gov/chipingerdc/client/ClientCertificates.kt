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
import kotlinx.coroutines.launch
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Bill
import zw.gov.chipingerdc.shared.model.Certificate
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.Property
import zw.gov.chipingerdc.shared.model.RevenueHead
import zw.gov.chipingerdc.shared.model.StandBeneficiary
import zw.gov.chipingerdc.shared.model.Tenancy
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private val FEE_HEADS = mapOf("RESIDENCE" to "CERT-RES", "CLEARANCE" to "CERT-CLR", "OWNERSHIP" to "CERT-OWN", "CESSION" to "CESSION", "BURIAL" to "BURIAL")
private val NEEDS_STAND = setOf("CLEARANCE", "OWNERSHIP", "CESSION")

@Composable
fun CertificatesScreen(ctx: CCtx) {
    val list by ctx.sdk.observe(Entities.CERTIFICATES, Certificate.serializer()).collectAsState(initial = emptyList())
    val bills by ctx.sdk.observe(Entities.BILLS, Bill.serializer()).collectAsState(initial = emptyList())
    AppScreen("Letters & certificates", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            item { PrimaryButton("Request a letter or certificate", onClick = { ctx.go(CScreen.RequestCertificate) }) }
            if (list.isEmpty()) item { Empty("No requests yet.") }
            items(list.sortedByDescending { it.createdAt }, key = { it.id }) { c ->
                SectionCard(c.kindLabel.ifBlank { c.kind }) {
                    Text(listOf(c.reference, c.subjectName.takeIf { it.isNotBlank() }?.let { "for $it" } ?: "", c.propertyLabel.ifBlank { c.address }, c.purpose,
                        c.otherPartyName).filter { it.isNotBlank() }.joinToString(" · "),
                        fontSize = 12.sp, color = CrdcColors.Muted)
                    Row { StatusChip(c.statusLabel.ifBlank { "Waiting to send" }, c.status) }
                    when (c.status) {
                        "FEE_DUE" -> if (c.feeBill != null && bills.firstOrNull { it.id == c.feeBill }?.status != "PAID")
                            PrimaryButton("Pay $${money(c.fee ?: "0")} fee", onClick = { ctx.go(CScreen.PayBills(listOf(c.feeBill))) })
                        "ISSUED" -> {
                            KeyValue("Number", c.number)
                            c.validUntil?.let { KeyValue("Valid until", prettyDate(it)) }
                            PrimaryButton("Open", onClick = { ctx.go(CScreen.CertificateView(c.id)) })
                        }
                        "REJECTED" -> KeyValue("Reason", c.decisionNote)
                    }
                }
            }
        }
    }
}

@Composable
fun RequestCertificateScreen(ctx: CCtx) {
    val props by ctx.sdk.observe(Entities.PROPERTIES, Property.serializer()).collectAsState(initial = emptyList())
    val rented by ctx.sdk.observe(Entities.TENANCIES, Tenancy.serializer()).collectAsState(initial = emptyList())
    val heads by ctx.sdk.observe(Entities.REVENUE_HEADS, RevenueHead.serializer()).collectAsState(initial = emptyList())
    var kind by remember { mutableStateOf("RESIDENCE") }
    var place by remember { mutableStateOf<Pair<String, String>?>(null) }
    var address by remember { mutableStateOf("") }
    var purpose by remember { mutableStateOf("") }
    var otherName by remember { mutableStateOf("") }
    var otherId by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") }
    var cemetery by remember { mutableStateOf("") }
    val people by ctx.sdk.observe(Entities.STAND_BENEFICIARIES, StandBeneficiary.serializer()).collectAsState(initial = emptyList())
    var forWho by remember { mutableStateOf("ME") }
    var sFirst by remember { mutableStateOf(ctx.me.firstName) }
    var sLast by remember { mutableStateOf(ctx.me.lastName) }
    var sName by remember { mutableStateOf("") }
    var sId by remember { mutableStateOf(ctx.me.nationalId) }
    var sPhone by remember { mutableStateOf("") }
    var sRel by remember { mutableStateOf("CHILD") }
    val owned = props.map { it.id to "Stand ${it.standNumber} · ${it.businessName.ifBlank { it.areaName.ifBlank { it.location } }}" }
    val places = if (kind == "RESIDENCE") owned + rented.filter { it.isActive }.map { it.property to "Stand ${it.standNumber} · ${it.areaName} (rented)" } else owned
    val fee = heads.firstOrNull { it.code == FEE_HEADS[kind] }?.defaultAmount
    val dateOk = date.isBlank() || Regex("""\d{4}-\d{2}-\d{2}""").matches(date)
    val ok = dateOk && when (kind) {
        "RESIDENCE" -> (place != null || address.isNotBlank()) && sFirst.isNotBlank() && sLast.isNotBlank() && sId.isNotBlank() &&
            (forWho == "ME" || place != null)
        "CESSION" -> place != null && otherName.isNotBlank() && otherId.isNotBlank()
        "BURIAL" -> otherName.isNotBlank() && date.isNotBlank() && cemetery.isNotBlank()
        else -> place != null
    }
    AppScreen("Request a letter or certificate", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Letter / certificate", Choices.certificateKinds, kind) { kind = it; place = null }
            if (kind != "BURIAL") Picker("Stand", places, place, { it.second }, { place = it })
            when (kind) {
                "RESIDENCE" -> {
                    val onStand = people.filter { it.property == place?.first && it.isActive }
                    val whoChoices = listOf("ME" to "Me (${ctx.me.fullName})") + onStand.map { it.id to "${it.fullName} – ${it.relationshipLabel}" } +
                        (if (place != null) listOf("NEW" to "Someone else on this stand") else emptyList())
                    ChoicePicker("Letter for", whoChoices, forWho) { who ->
                        forWho = who
                        val b = onStand.firstOrNull { it.id == who }
                        when {
                            who == "ME" -> { sFirst = ctx.me.firstName; sLast = ctx.me.lastName; sId = ctx.me.nationalId; sPhone = ctx.me.phone }
                            b != null -> { sFirst = b.fullName.substringBeforeLast(" "); sLast = b.fullName.substringAfterLast(" ", ""); sId = b.nationalId; sPhone = b.phone; sRel = b.relationship }
                            else -> { sFirst = ""; sLast = ""; sId = ""; sPhone = "" }
                        }
                    }
                    Field("Name", sFirst, { sFirst = it })
                    Field("Surname", sLast, { sLast = it })
                    Field("ID number", sId, { sId = it.uppercase() })
                    if (forWho == "NEW") {
                        Field("Phone", sPhone, { sPhone = it })
                        ChoicePicker("Relationship", Choices.relationships2, sRel) { sRel = it }
                    }
                    if (place == null) Field("Where I live (village, street, stand)", address, { address = it })
                    Field("What it is for (bank, school, passport …)", purpose, { purpose = it })
                }
                "CLEARANCE", "OWNERSHIP" -> Field("What it is for (sale, bank loan …)", purpose, { purpose = it })
                "CESSION" -> {
                    Field("New owner's full name", otherName, { otherName = it })
                    Field("New owner's National ID", otherId, { otherId = it })
                    Field("Date of the agreement of sale (YYYY-MM-DD)", date, { date = it })
                }
                "BURIAL" -> {
                    Field("Name of the deceased", otherName, { otherName = it })
                    Field("Their National ID", otherId, { otherId = it })
                    Field("Date of death (YYYY-MM-DD)", date, { date = it })
                    Field("Cemetery", cemetery, { cemetery = it })
                }
            }
            fee?.takeIf { (it.toDoubleOrNull() ?: 0.0) > 0 }?.let { KeyValue("Fee", "USD ${money(it)}") }
            PrimaryButton("Send request", enabled = ok, onClick = {
                val id = ctx.sdk.newId()
                val label = Choices.certificateKinds.first { it.first == kind }.second
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(sending)"); put("kind", kind); put("kind_label", label); put("purpose", purpose)
                    put("address", address); put("other_party_name", otherName); put("status", "FEE_DUE"); put("status_label", "Waiting to send")
                    put("property_label", place?.second ?: ""); put("created_at", ctx.sdk.nowIso()); put("updated_at", ctx.sdk.nowIso())
                    put("subject_name", "${sFirst.trim()} ${sLast.trim()}".trim())
                }
                ctx.sdk.enqueue("certificate.request", label, Entities.CERTIFICATES, id, opt) {
                    put("id", id); put("kind", kind); place?.let { put("property", it.first) }; put("address", address); put("purpose", purpose)
                    put("other_party_name", otherName); put("other_party_id", otherId); if (date.isNotBlank()) put("event_date", date); put("place", cemetery)
                    if (kind == "RESIDENCE") {
                        put("subject_name", "${sFirst.trim()} ${sLast.trim()}".trim()); put("subject_id", sId.trim()); put("subject_phone", sPhone)
                        when (forWho) {
                            "ME" -> put("for_self", true)
                            "NEW" -> put("subject_relationship", sRel)
                            else -> put("beneficiary", forWho)
                        }
                    }
                }
                if (kind == "RESIDENCE" && forWho == "NEW") ctx.sdk.store.resetCursor(Entities.STAND_BENEFICIARIES)
                listOf(Entities.ACCOUNTS, Entities.BILLS).forEach { ctx.sdk.store.resetCursor(it) }
                ctx.back()
            })
        }
    }
}

