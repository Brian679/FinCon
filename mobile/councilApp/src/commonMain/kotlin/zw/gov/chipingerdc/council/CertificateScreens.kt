package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Certificate
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

/** Letters & certificates residents asked for, for the office that issues them (paid requests first). */
@Composable
fun CertificatesToIssueScreen(ctx: Ctx) {
    var q by remember { mutableStateOf("") }
    val list by ctx.sdk.search(Entities.CERTIFICATES, q, Certificate.serializer()).collectAsState(initial = emptyList())
    AppScreen("Letters & certificates", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        Field("Search", q, { q = it }, Modifier.padding(12.dp))
        ListScreen {
            if (list.isEmpty()) item { Empty("No requests.") }
            items(list.sortedWith(compareBy({ if (it.status == "PROCESSING") 0 else 1 }, { it.createdAt })), key = { it.id }) { c ->
                RowCard("${c.kindLabel} – ${c.applicantName}", "${c.reference} · ${c.propertyLabel.ifBlank { c.address }}\n${c.purpose}".trim(),
                    c.number.ifBlank { null }, c.statusLabel, c.status) { ctx.go(Screen.CertificateDetail(c.id)) }
            }
        }
    }
}

@Composable
fun CertificateDetailScreen(ctx: Ctx, id: String) {
    val cert by ctx.sdk.observeOne(Entities.CERTIFICATES, id, Certificate.serializer()).collectAsState(initial = null)
    AppScreen("Letter / certificate", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val c = cert ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${c.reference} – ${c.kindLabel}") {
                KeyValue("Applicant", c.applicantName); KeyValue("National ID", c.nationalId); KeyValue("Phone", c.phone)
                if (c.subjectName.isNotBlank()) KeyValue("Letter is for", "${c.subjectName} · ${c.subjectId} · ${c.subjectRelationship} · ${c.subjectPhone}")
                if (c.propertyLabel.isNotBlank()) KeyValue("Stand", c.propertyLabel)
                if (c.address.isNotBlank()) KeyValue("Address", c.address)
                KeyValue("Account", "${c.accountNumber} · balance $${money(c.accountBalance)}")
                if (c.purpose.isNotBlank()) KeyValue("Purpose", c.purpose)
                if (c.otherPartyName.isNotBlank()) KeyValue(if (c.kind == "BURIAL") "Deceased" else "New owner", "${c.otherPartyName} ${c.otherPartyId}".trim())
                c.eventDate?.let { KeyValue(if (c.kind == "BURIAL") "Date of death" else "Date of sale", prettyDate(it)) }
                if (c.place.isNotBlank()) KeyValue("Cemetery", c.place)
                c.fee?.let { KeyValue("Fee", "$${money(it)}" + if (c.feePaid) " – paid" else " – not paid") }
                if (c.number.isNotBlank()) KeyValue("Number", c.number)
                c.validUntil?.let { KeyValue("Valid until", prettyDate(it)) }
                if (c.decisionNote.isNotBlank()) KeyValue("Note", c.decisionNote)
                Row { StatusChip(c.statusLabel, c.status) }
            }
            if (c.kind == "CLEARANCE" && (c.accountBalance.toDoubleOrNull() ?: 0.0) > 0) InfoBox("Account owes $${money(c.accountBalance)}", CrdcColors.Danger)
            if (c.status == "PROCESSING" && ctx.me.can("certificates.issue")) {
                ActionPanel("Issue or reject", listOf(FieldSpec("note", "Note (required to reject)", "multiline")),
                    listOf("issue" to "Issue", "reject" to "Reject")) { action, v ->
                    ctx.sdk.markPending(Entities.CERTIFICATES, c.id, "Decision queued")
                    ctx.sdk.enqueue("certificate.action", "${c.reference}: $action", Entities.CERTIFICATES, c.id) {
                        put("certificate", c.id); put("action", action); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}
