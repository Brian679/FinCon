package zw.gov.chipingerdc.council

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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.Asset
import zw.gov.chipingerdc.shared.model.AuditFinding
import zw.gov.chipingerdc.shared.model.BuildingPlan
import zw.gov.chipingerdc.shared.model.Choices
import zw.gov.chipingerdc.shared.model.CommunityActivity
import zw.gov.chipingerdc.shared.model.CouncilMeeting
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.IctTicket
import zw.gov.chipingerdc.shared.model.Incident
import zw.gov.chipingerdc.shared.model.Policy
import zw.gov.chipingerdc.shared.model.Project
import zw.gov.chipingerdc.shared.model.Resolution
import zw.gov.chipingerdc.shared.model.Risk
import zw.gov.chipingerdc.shared.model.StandApplication
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.Progress
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.isPast
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

private fun isHeadOf(ctx: Ctx, dept: String) = ctx.me.isCeo || (ctx.me.isHead && ctx.me.department == dept)

// ------------------------------------------------------- social services
@Composable
fun StandDetailScreen(ctx: Ctx, id: String) {
    val st by ctx.sdk.observeOne(Entities.STANDS, id, StandApplication.serializer()).collectAsState(initial = null)
    AppScreen("Stand application", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val s = st ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${s.reference} – ${s.applicantName}") {
                KeyValue("National ID", s.nationalId); KeyValue("Phone", s.phone); KeyValue("Stand type", s.standTypeLabel)
                KeyValue("Preferred location", "${s.preferredLocation} · Ward ${s.ward ?: "-"}"); KeyValue("Allocated stand", s.allocatedStand)
                Row { StatusChip(s.statusLabel, s.status) }
            }
            if (s.status in listOf("RECEIVED", "SHORTLISTED") && ctx.me.can("stands.manage")) {
                val buttons = buildList {
                    if (s.status == "RECEIVED") add("shortlist" to "Shortlist (officer)")
                    if (ctx.me.can("stands.allocate")) add("allocate" to "Allocate stand (Director)")
                    add("reject" to "Reject")
                }
                ActionPanel("Process application", listOf(FieldSpec("allocated_stand", "Stand number to allocate"), FieldSpec("note", "Note", "multiline")),
                    buttons) { action, v ->
                    ctx.sdk.enqueue("stand.action", "Stand ${s.reference}: $action", Entities.STANDS, s.id) {
                        put("stand", s.id); put("action", action); put("allocated_stand", v["allocated_stand"] ?: ""); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

@Composable
fun IncidentsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.INCIDENTS, Incident.serializer()).collectAsState(initial = emptyList())
    AppScreen("Incidents & disasters", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("incidents.manage")) PrimaryButton("+ Report incident", color = CrdcColors.Danger, onClick = { ctx.go(Screen.NewIncident) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No incidents.") }
            items(list, key = { it.id }) { i ->
                RowCard(i.title, "${i.reference} · ${i.incidentTypeLabel} · ${i.location}, ward ${i.ward ?: "-"}\n${prettyDate(i.occurredAt)} · ${i.householdsAffected} households",
                    null, i.statusLabel, if (i.status == "CLOSED") "CLOSED" else "URGENT", i.localNote) { ctx.go(Screen.IncidentDetail(i.id)) }
            }
        }
    }
}

@Composable
fun NewIncidentScreen(ctx: Ctx) {
    var type by remember { mutableStateOf("FIRE") }
    var title by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var households by remember { mutableStateOf("0") }
    var injured by remember { mutableStateOf("0") }
    var deaths by remember { mutableStateOf("0") }
    var livestock by remember { mutableStateOf("0") }
    var crops by remember { mutableStateOf("0") }
    AppScreen("Report incident", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Type", Choices.incidentTypes, type) { type = it }
            Field("Title", title, { title = it }); Field("Location / village", location, { location = it }); Field("Ward", ward, { ward = it }, number = true)
            Field("What happened", description, { description = it }, singleLine = false, minLines = 3)
            Field("Households affected", households, { households = it }, number = true); Field("People injured", injured, { injured = it }, number = true)
            Field("Deaths", deaths, { deaths = it }, number = true); Field("Livestock lost", livestock, { livestock = it }, number = true)
            Field("Crops destroyed (ha)", crops, { crops = it }, number = true)
            PrimaryButton("Report", enabled = title.isNotBlank() && location.isNotBlank(), color = CrdcColors.Danger, onClick = {
                val id = ctx.sdk.newId(); val now = ctx.sdk.nowIso()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("title", title); put("incident_type", type); put("location", location)
                    put("occurred_at", now); put("status", "REPORTED"); put("status_label", "Pending sync"); put("updated_at", now)
                    put("households_affected", households.toIntOrNull() ?: 0); put("local_note", "Saved on phone – HOD & CEO alerted on sync")
                }
                ctx.sdk.enqueue("incident.create", "Incident: $title", Entities.INCIDENTS, id, opt) {
                    put("id", id); put("incident_type", type); put("title", title); put("location", location); ward.toIntOrNull()?.let { put("ward", it) }
                    put("description", description.ifBlank { title }); put("households_affected", households.toIntOrNull() ?: 0)
                    put("people_injured", injured.toIntOrNull() ?: 0); put("deaths", deaths.toIntOrNull() ?: 0)
                    put("livestock_lost", livestock.toIntOrNull() ?: 0); put("crops_hectares", crops.ifBlank { "0" }); put("captured_at", now)
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun IncidentDetailScreen(ctx: Ctx, id: String) {
    val inc by ctx.sdk.observeOne(Entities.INCIDENTS, id, Incident.serializer()).collectAsState(initial = null)
    AppScreen("Incident", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val i = inc ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${i.reference} – ${i.title}") {
                KeyValue("Type", i.incidentTypeLabel); KeyValue("Where", "${i.location}, ward ${i.ward ?: "-"}"); KeyValue("When", prettyDate(i.occurredAt))
                KeyValue("Households", i.householdsAffected.toString()); KeyValue("Injured / deaths", "${i.peopleInjured} / ${i.deaths}")
                KeyValue("Livestock / crops", "${i.livestockLost} / ${i.cropsHectares} ha"); KeyValue("Lead officer", i.leadOfficerName)
                Text(i.description); KeyValue("Response log", i.response)
                Row { StatusChip(i.statusLabel, i.status) }
                i.localNote?.let { InfoBox(it) }
            }
            if (i.status != "CLOSED" && ctx.me.can("incidents.manage")) {
                val statuses = Choices.incidentStatuses.filter { it.first != "CLOSED" || isHeadOf(ctx, "SOCIAL") }
                ActionPanel("Response update", listOf(FieldSpec("response", "Action taken / relief given", "multiline"),
                    FieldSpec("households_affected", "Households affected", "number", initial = i.householdsAffected.toString()),
                    FieldSpec("status", "Status", "choice", statuses, i.status)), listOf("update" to "Save update")) { _, v ->
                    ctx.sdk.markPending(Entities.INCIDENTS, i.id, "Update queued")
                    ctx.sdk.enqueue("incident.update", "Incident ${i.reference} update", Entities.INCIDENTS, i.id) {
                        put("incident", i.id); put("response", v["response"] ?: ""); put("status", v["status"] ?: "")
                        v["households_affected"]?.toIntOrNull()?.let { put("households_affected", it) }
                    }
                }
            }
        }
    }
}

@Composable
fun ActivitiesScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.ACTIVITIES, CommunityActivity.serializer()).collectAsState(initial = emptyList())
    AppScreen("Community programmes & campaigns", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (ctx.me.can("activities.manage")) PrimaryButton("+ Plan / record an activity", onClick = { ctx.go(Screen.NewActivity) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No activities.") }
            items(list.sortedByDescending { it.date }, key = { it.id }) { a ->
                RowCard(a.title, "${a.reference} · ${a.activityTypeLabel}\n${prettyDate(a.date)} · ward ${a.ward ?: "-"} · ${a.participants} people · ${a.officerName}",
                    null, a.statusLabel, a.status, a.localNote) { ctx.go(Screen.ActivityDetail(a.id)) }
            }
        }
    }
}

@Composable
fun NewActivityScreen(ctx: Ctx) {
    var type by remember { mutableStateOf("HYGIENE") }
    var title by remember { mutableStateOf("") }
    var venue by remember { mutableStateOf("") }
    var ward by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(ctx.sdk.nowIso().take(10)) }
    var participants by remember { mutableStateOf("") }
    var report by remember { mutableStateOf("") }
    AppScreen("Community activity", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Type", Choices.activityTypes, type) { type = it }
            Field("Title", title, { title = it }); Field("Venue", venue, { venue = it }); Field("Ward", ward, { ward = it }, number = true)
            Field("Date (YYYY-MM-DD)", date, { date = it })
            InfoBox("Already held? Fill in participants and the report – it goes straight to your head of department for verification.")
            Field("Participants", participants, { participants = it }, number = true)
            Field("Report (outcome, issues raised)", report, { report = it }, singleLine = false, minLines = 3)
            PrimaryButton("Save", enabled = title.isNotBlank() && date.length == 10, onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("title", title); put("activity_type", type); put("date", date)
                    put("department", ctx.me.department); put("status", if (report.isBlank()) "PLANNED" else "DONE"); put("status_label", "Pending sync")
                    put("officer_id", ctx.me.id); put("officer_name", ctx.me.fullName); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("activity.create", "Activity: $title", Entities.ACTIVITIES, id, opt) {
                    put("id", id); put("activity_type", type); put("title", title); put("venue", venue); ward.toIntOrNull()?.let { put("ward", it) }
                    put("date", date); put("department", ctx.me.department)
                    if (report.isNotBlank()) { put("report", report); put("participants", participants.toIntOrNull() ?: 0) }
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun ActivityDetailScreen(ctx: Ctx, id: String) {
    val act by ctx.sdk.observeOne(Entities.ACTIVITIES, id, CommunityActivity.serializer()).collectAsState(initial = null)
    AppScreen("Activity", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val a = act ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${a.reference} – ${a.title}") {
                KeyValue("Type", a.activityTypeLabel); KeyValue("Department", a.departmentLabel); KeyValue("Date", prettyDate(a.date))
                KeyValue("Venue", "${a.venue} · ward ${a.ward ?: "-"}"); KeyValue("Participants", a.participants.toString()); KeyValue("Officer", a.officerName)
                KeyValue("Report", a.report); Row { StatusChip(a.statusLabel, a.status) }
                a.localNote?.let { InfoBox(it) }
            }
            if (a.localNote == null && a.status in listOf("PLANNED", "DONE") && ctx.me.can("activities.manage") && a.officerId == ctx.me.id) {
                ActionPanel("Submit activity report (stage 1: officer)", listOf(FieldSpec("participants", "Participants", "number", initial = a.participants.toString()),
                    FieldSpec("report", "Report", "multiline", initial = a.report)), listOf("report" to "Submit to Head of Department")) { _, v ->
                    ctx.sdk.markPending(Entities.ACTIVITIES, a.id, "Report queued")
                    ctx.sdk.enqueue("activity.report", "Activity report ${a.reference}", Entities.ACTIVITIES, a.id) {
                        put("activity", a.id); put("report", v["report"] ?: ""); put("participants", v["participants"]?.toIntOrNull() ?: 0)
                    }
                }
            }
            if (a.localNote == null && a.status == "DONE" && isHeadOf(ctx, a.department) && a.officerId != ctx.me.id) {
                ActionPanel("Verification (stage 2: Head of Department)", listOf(FieldSpec("note", "Comment")),
                    listOf("verify" to "Verify report", "return" to "Return to officer")) { action, v ->
                    ctx.sdk.markPending(Entities.ACTIVITIES, a.id, "Decision queued")
                    ctx.sdk.enqueue("activity.verify", "Verify ${a.reference}", Entities.ACTIVITIES, a.id) {
                        put("activity", a.id); put("approve", action == "verify"); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------- technical services
@Composable
fun ProjectDetailScreen(ctx: Ctx, id: String) {
    val pr by ctx.sdk.observeOne(Entities.PROJECTS, id, Project.serializer()).collectAsState(initial = null)
    AppScreen("Project", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val p = pr ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${p.code} – ${p.name}") {
                KeyValue("Category", p.categoryLabel); KeyValue("Where", "${p.location} · ward ${p.ward ?: "-"}")
                KeyValue("Budget", "$${money(p.budget)} · ${p.funder.ifBlank { "Council" }}"); KeyValue("Dates", "${prettyDate(p.startDate)} – ${prettyDate(p.endDate)}")
                Progress(p.progress); Text("${p.progress}% complete · ${p.statusLabel}", fontSize = 12.sp)
            }
            if (ctx.me.can("projects.manage")) {
                ActionPanel("Site progress update", listOf(FieldSpec("progress", "Progress %", "number", initial = p.progress.toString()),
                    FieldSpec("status", "Status", "choice", Choices.projectStatuses, p.status), FieldSpec("note", "Site report", "multiline")),
                    listOf("update" to "Save")) { _, v ->
                    ctx.sdk.enqueue("project.update", "Project ${p.code} progress", Entities.PROJECTS, p.id) {
                        put("project", p.id); v["progress"]?.toIntOrNull()?.let { put("progress", it) }; put("status", v["status"] ?: ""); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

@Composable
fun PlansScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.BUILDING_PLANS, BuildingPlan.serializer()).collectAsState(initial = emptyList())
    AppScreen("Building plans", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No building plans.") }
            items(list, key = { it.id }) { p ->
                val late = isPast(p.dueAt) && p.status in listOf("SUBMITTED", "REVIEW", "RECOMMEND")
                RowCard("${p.applicantName} – stand ${p.standNumber}", "${p.reference} · ${p.developmentTypeLabel} · ${p.location}\nDecision due ${prettyDate(p.dueAt)}" +
                    if (late) " – PAST CHARTER DEADLINE" else "", null, p.statusLabel, if (late) "URGENT" else p.status, p.localNote) { ctx.go(Screen.PlanDetail(p.id)) }
            }
        }
    }
}

@Composable
fun PlanDetailScreen(ctx: Ctx, id: String) {
    val pl by ctx.sdk.observeOne(Entities.BUILDING_PLANS, id, BuildingPlan.serializer()).collectAsState(initial = null)
    AppScreen("Building plan", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val p = pl ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${p.reference} – ${p.applicantName}") {
                KeyValue("Stand", "${p.standNumber}, ${p.location}"); KeyValue("Development", p.developmentTypeLabel); KeyValue("Floor area", "${p.floorArea} m²")
                KeyValue("Description", p.description); KeyValue("Fee", "$${money(p.fee)} · ${p.billStatus ?: "no bill"}")
                KeyValue("Charter deadline", prettyDate(p.dueAt)); KeyValue("Review notes", p.reviewNotes); KeyValue("Decision", p.decisionNotes)
                KeyValue("Inspections", p.inspectionLog); Row { StatusChip(p.statusLabel, p.status) }
                p.localNote?.let { InfoBox(it) }
            }
            if (p.localNote == null) {
                val me = ctx.me
                val (title, buttons) = when {
                    p.status in listOf("SUBMITTED", "REVIEW") && me.can("plans.review") ->
                        "Technical review (stage 1)" to listOf("recommend" to "Recommend for approval", "return" to "Return for corrections")
                    p.status == "RECOMMEND" && me.can("plans.approve") && p.reviewedById != me.id ->
                        "District Engineer decision (stage 2)" to listOf("approve" to "Approve plan", "reject" to "Reject")
                    p.status in listOf("APPROVED", "BUILDING") && me.can("plans.review") ->
                        "Site inspection (stage 3)" to listOf("inspect" to "Record inspection", "complete" to "Issue completion certificate")
                    else -> null to emptyList()
                }
                if (title != null) ActionPanel(title, listOf(FieldSpec("note", "Notes / findings", "multiline")), buttons) { action, v ->
                    ctx.sdk.markPending(Entities.BUILDING_PLANS, p.id, "Decision queued")
                    ctx.sdk.enqueue("plan.action", "Plan ${p.reference}: $action", Entities.BUILDING_PLANS, p.id) {
                        put("plan", p.id); put("action", action); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

@Composable
fun AssetsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.ASSETS, Asset.serializer()).collectAsState(initial = emptyList())
    var onlyFaulty by remember { mutableStateOf(false) }
    val shown = if (onlyFaulty) list.filter { it.condition in listOf("POOR", "BROKEN") } else list
    AppScreen("Assets & infrastructure", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ChoicePicker("Show", listOf("ALL" to "All assets", "FAULTY" to "Needing repair"), if (onlyFaulty) "FAULTY" else "ALL") { onlyFaulty = it == "FAULTY" }
        ListScreen {
            if (shown.isEmpty()) item { Empty("No assets.") }
            items(shown, key = { it.id }) { a ->
                RowCard(a.name, "${a.assetNumber} · ${a.categoryLabel} · ${a.location} · ${a.departmentLabel}", null, a.conditionLabel,
                    when (a.condition) { "BROKEN" -> "URGENT"; "POOR" -> "PENDING"; else -> "VALID" }, a.localNote) { ctx.go(Screen.AssetDetail(a.id)) }
            }
        }
    }
}

@Composable
fun AssetDetailScreen(ctx: Ctx, id: String) {
    val asset by ctx.sdk.observeOne(Entities.ASSETS, id, Asset.serializer()).collectAsState(initial = null)
    AppScreen("Asset", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val a = asset ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${a.assetNumber} – ${a.name}") {
                KeyValue("Category", a.categoryLabel); KeyValue("Department", a.departmentLabel); KeyValue("Serial / reg.", a.serialNumber)
                KeyValue("Location", "${a.location} · ward ${a.ward ?: "-"}"); KeyValue("Cost / book value", "$${money(a.cost)} / $${money(a.bookValue)}")
                KeyValue("Custodian", a.custodianName); KeyValue("Status", a.statusLabel); Row { StatusChip(a.conditionLabel, if (a.condition == "BROKEN") "URGENT" else a.condition) }
                a.localNote?.let { InfoBox(it) }
            }
            SectionCard("Maintenance & condition history") {
                if (a.history.isEmpty()) Text("No history.", color = CrdcColors.Muted)
                a.history.forEach { KeyValue("${it.date} · ${it.condition}", "${it.workDone} ($${money(it.cost)})") }
            }
            if (ctx.me.can("assets.manage", "assets.condition")) {
                ActionPanel("Field condition report / repair", listOf(FieldSpec("condition", "Condition now", "choice", Choices.assetConditions, a.condition),
                    FieldSpec("note", "Observation / work done", "multiline"), FieldSpec("cost", "Repair cost (USD)", "number")), listOf("save" to "Save")) { _, v ->
                    ctx.sdk.markPending(Entities.ASSETS, a.id, "Condition report queued")
                    ctx.sdk.enqueue("asset.condition", "Asset ${a.assetNumber} condition", Entities.ASSETS, a.id) {
                        put("asset", a.id); put("condition", v["condition"] ?: a.condition); put("note", v["note"] ?: ""); put("cost", v["cost"]?.ifBlank { "0" } ?: "0")
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------ internal audit
@Composable
fun FindingDetailScreen(ctx: Ctx, id: String) {
    val fd by ctx.sdk.observeOne(Entities.AUDIT_FINDINGS, id, AuditFinding.serializer()).collectAsState(initial = null)
    AppScreen("Audit finding", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val f = fd ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${f.reference} – ${f.title}") {
                KeyValue("Audit type", f.auditTypeLabel); KeyValue("Department", f.departmentLabel); KeyValue("Risk", f.riskRatingLabel)
                KeyValue("Finding", f.finding); KeyValue("Recommendation", f.recommendation); KeyValue("Management response", f.managementResponse)
                KeyValue("Target date", prettyDate(f.implementationDate)); Row { StatusChip(f.statusLabel, f.status) }
            }
            if (f.status == "OPEN" && ctx.me.can("audit.respond") && (ctx.me.department == f.department || ctx.me.isCeo)) {
                ActionPanel("Management response (Head of Department)", listOf(FieldSpec("response", "Agreed action", "multiline"),
                    FieldSpec("date", "Implementation date (YYYY-MM-DD)")), listOf("respond" to "Submit response")) { _, v ->
                    ctx.sdk.enqueue("finding.respond", "Response to ${f.reference}", Entities.AUDIT_FINDINGS, f.id) {
                        put("finding", f.id); put("response", v["response"] ?: ""); v["date"]?.takeIf { it.length == 10 }?.let { put("date", it) }
                    }
                }
            }
        }
    }
}

@Composable
fun RisksScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.RISKS, Risk.serializer()).collectAsState(initial = emptyList())
    AppScreen("Risk register", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No risks recorded.") }
            items(list.sortedByDescending { it.score }, key = { it.id }) { r ->
                SectionCard("${r.reference} – ${r.title}") {
                    Text("${r.departmentLabel} · ${r.categoryLabel} · owner ${r.ownerName}", fontSize = 12.sp, color = CrdcColors.Muted)
                    Row { StatusChip("${r.rating} (${r.likelihood}×${r.impact}=${r.score})", if (r.rating in listOf("HIGH", "CRITICAL")) "URGENT" else "PENDING") }
                    KeyValue("Risk", r.description); KeyValue("Controls", r.existingControls); KeyValue("Mitigation", r.mitigation)
                    KeyValue("Review", prettyDate(r.reviewDate)); KeyValue("Status", r.statusLabel)
                }
            }
        }
    }
}

// ----------------------------------------------------------- administration
@Composable
fun MeetingsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.MEETINGS, CouncilMeeting.serializer()).collectAsState(initial = emptyList())
    AppScreen("Council meetings", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("Resolutions tracker", color = CrdcColors.Blue, onClick = { ctx.go(Screen.Resolutions) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No meetings.") }
            items(list.sortedByDescending { it.date }, key = { it.id }) { m ->
                RowCard(m.title, "${m.reference} · ${m.meetingTypeLabel}\n${prettyDate(m.date)} · ${m.venue}", null, m.statusLabel, m.status) { ctx.go(Screen.MeetingDetail(m.id)) }
            }
        }
    }
}

@Composable
fun MeetingDetailScreen(ctx: Ctx, id: String) {
    val m by ctx.sdk.observeOne(Entities.MEETINGS, id, CouncilMeeting.serializer()).collectAsState(initial = null)
    val res by ctx.sdk.observe(Entities.RESOLUTIONS, Resolution.serializer()).collectAsState(initial = emptyList())
    AppScreen("Meeting", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val mt = m ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(mt.title) {
                KeyValue("Type", mt.meetingTypeLabel); KeyValue("Date", prettyDate(mt.date)); KeyValue("Venue", mt.venue); KeyValue("Status", mt.statusLabel)
                KeyValue("Agenda", mt.agenda); KeyValue("Minutes", mt.minutes)
            }
            SectionCard("Resolutions") {
                res.filter { it.meeting == mt.id }.forEach { r -> RowCard(r.number, r.text, null, r.statusLabel, r.status) { ctx.go(Screen.ResolutionDetail(r.id)) } }
            }
        }
    }
}

@Composable
fun ResolutionsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.RESOLUTIONS, Resolution.serializer()).collectAsState(initial = emptyList())
    AppScreen("Council resolutions", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No resolutions.") }
            items(list, key = { it.id }) { r ->
                val late = r.dueDate != null && r.status !in listOf("DONE", "RESCINDED") && isPast(r.dueDate + "T23:59:59Z")
                RowCard(r.text.take(80), "${r.number} · ${r.departmentLabel} · ${r.responsibleName}\nDue ${prettyDate(r.dueDate)}${if (late) " – OVERDUE" else ""}",
                    null, r.statusLabel, if (late) "URGENT" else r.status, r.localNote) { ctx.go(Screen.ResolutionDetail(r.id)) }
            }
        }
    }
}

@Composable
fun ResolutionDetailScreen(ctx: Ctx, id: String) {
    val rs by ctx.sdk.observeOne(Entities.RESOLUTIONS, id, Resolution.serializer()).collectAsState(initial = null)
    AppScreen("Resolution", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val r = rs ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard(r.number) {
                Text(r.text); KeyValue("Meeting", r.meetingTitle); KeyValue("Department", r.departmentLabel); KeyValue("Responsible", r.responsibleName)
                KeyValue("Due", prettyDate(r.dueDate)); KeyValue("Progress", r.progressNote); Row { StatusChip(r.statusLabel, r.status) }
                r.localNote?.let { InfoBox(it) }
            }
            if (r.localNote == null && (r.responsibleId == ctx.me.id || ctx.me.can("meetings.manage") || isHeadOf(ctx, r.department))) {
                ActionPanel("Report implementation", listOf(FieldSpec("status", "Status", "choice", Choices.resolutionStatuses, r.status),
                    FieldSpec("note", "Progress note", "multiline")), listOf("save" to "Save")) { _, v ->
                    ctx.sdk.markPending(Entities.RESOLUTIONS, r.id, "Update queued")
                    ctx.sdk.enqueue("resolution.update", "Resolution ${r.number}", Entities.RESOLUTIONS, r.id) {
                        put("resolution", r.id); put("status", v["status"] ?: r.status); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

@Composable
fun TicketsScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.ICT_TICKETS, IctTicket.serializer()).collectAsState(initial = emptyList())
    AppScreen("ICT helpdesk", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        PrimaryButton("+ Raise a ticket", onClick = { ctx.go(Screen.NewTicket) })
        ListScreen {
            if (list.isEmpty()) item { Empty("No tickets.") }
            items(list, key = { it.id }) { t ->
                RowCard(t.subject, "${t.reference} · ${t.categoryLabel} · ${t.raisedByName}", t.priorityLabel, t.statusLabel, t.status, t.localNote) {
                    ctx.go(Screen.TicketDetail(t.id))
                }
            }
        }
    }
}

@Composable
fun NewTicketScreen(ctx: Ctx) {
    var category by remember { mutableStateOf("HW") }
    var subject by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("NORMAL") }
    AppScreen("Raise ICT ticket", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            ChoicePicker("Category", Choices.ictCategories, category) { category = it }
            Field("Subject", subject, { subject = it }); Field("Describe the problem", description, { description = it }, singleLine = false, minLines = 3)
            ChoicePicker("Priority", Choices.priorities, priority) { priority = it }
            PrimaryButton("Raise ticket", enabled = subject.isNotBlank() && description.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val opt = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("subject", subject); put("raised_by_id", ctx.me.id); put("raised_by_name", ctx.me.fullName)
                    put("status", "OPEN"); put("status_label", "Pending sync"); put("updated_at", ctx.sdk.nowIso())
                }
                ctx.sdk.enqueue("ict.create", "ICT: $subject", Entities.ICT_TICKETS, id, opt) {
                    put("id", id); put("category", category); put("subject", subject); put("description", description); put("priority", priority)
                }
                ctx.back()
            })
        }
    }
}

@Composable
fun TicketDetailScreen(ctx: Ctx, id: String) {
    val tk by ctx.sdk.observeOne(Entities.ICT_TICKETS, id, IctTicket.serializer()).collectAsState(initial = null)
    AppScreen("ICT ticket", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val t = tk ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            SectionCard("${t.reference} – ${t.subject}") {
                KeyValue("Raised by", t.raisedByName); KeyValue("Category", t.categoryLabel); KeyValue("Priority", t.priorityLabel)
                Text(t.description); KeyValue("Resolution", t.resolution); Row { StatusChip(t.statusLabel, t.status) }
                t.localNote?.let { InfoBox(it) }
            }
            if (t.localNote == null) {
                val buttons = buildList {
                    if (ctx.me.can("ict.manage") && t.status in listOf("OPEN", "IN_PROGRESS")) { add("take" to "Take ticket"); add("resolve" to "Resolved") }
                    if (t.status == "RESOLVED" && (t.raisedById == ctx.me.id || ctx.me.can("ict.manage"))) add("close" to "Confirm fixed – close")
                }
                if (buttons.isNotEmpty()) ActionPanel("Action", listOf(FieldSpec("note", "Notes", "multiline")), buttons) { action, v ->
                    ctx.sdk.markPending(Entities.ICT_TICKETS, t.id, "Update queued")
                    ctx.sdk.enqueue("ict.action", "Ticket ${t.reference}: $action", Entities.ICT_TICKETS, t.id) {
                        put("ticket", t.id); put("action", action); put("note", v["note"] ?: "")
                    }
                }
            }
        }
    }
}

@Composable
fun PoliciesScreen(ctx: Ctx) {
    val list by ctx.sdk.observe(Entities.POLICIES, Policy.serializer()).collectAsState(initial = emptyList())
    AppScreen("Policies & by-laws", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ListScreen {
            if (list.isEmpty()) item { Empty("No policies.") }
            items(list, key = { it.id }) { p ->
                SectionCard("${p.title} v${p.version}") {
                    Text("${p.kindLabel} · ${p.departmentLabel}", fontSize = 12.sp, color = CrdcColors.Muted)
                    Text(p.summary); KeyValue("Adopted", prettyDate(p.adoptedOn)); KeyValue("Review by", prettyDate(p.reviewDate))
                    Row { StatusChip(p.statusLabel, if (p.status == "ADOPTED") "ACTIVE" else "PENDING") }
                }
            }
        }
    }
}
