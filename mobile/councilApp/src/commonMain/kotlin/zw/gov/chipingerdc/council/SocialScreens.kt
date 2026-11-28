package zw.gov.chipingerdc.council

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
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
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import zw.gov.chipingerdc.shared.model.ClientAccount
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.model.StaffMember
import zw.gov.chipingerdc.shared.ui.ActionPanel
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.ChoicePicker
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.Field
import zw.gov.chipingerdc.shared.ui.FieldSpec
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.KeyValue
import zw.gov.chipingerdc.shared.ui.Kpi
import zw.gov.chipingerdc.shared.ui.ListScreen
import zw.gov.chipingerdc.shared.ui.Picker
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.RowCard
import zw.gov.chipingerdc.shared.ui.ScrollColumn
import zw.gov.chipingerdc.shared.ui.SecondaryButton
import zw.gov.chipingerdc.shared.ui.SectionCard
import zw.gov.chipingerdc.shared.ui.StatusChip
import zw.gov.chipingerdc.shared.ui.money
import zw.gov.chipingerdc.shared.ui.prettyDate

/*
 * Social Services registers (CAMPFIRE wildlife database, hunting quotas, trophy hunts, sand / mining /
 * forestry permits, farms, water points, social welfare) and by-law fines – all offline-first.
 * Each register is described once (fields, list line, actions) and drawn by the same three screens.
 */

internal fun JsonObject.s(k: String) = (this[k] as? JsonPrimitive)?.contentOrNull ?: ""
internal fun JsonObject.list(k: String) = (this[k] as? JsonArray)?.map { it.jsonObject } ?: emptyList()

/** One input. kind: text, number, int, date, multiline, choice, bool, account (council account picker), ref (another register). */
data class RField(val key: String, val label: String, val kind: String = "text", val choices: List<Pair<String, String>> = emptyList(),
                  val required: Boolean = false, val ref: String = "")

data class RAction(val title: String, val op: String, val idKey: String, val buttons: List<Pair<String, String>>, val fields: List<FieldSpec> = emptyList(),
                   val caps: List<String>, val visible: (JsonObject, Ctx) -> Boolean)

data class RegisterSpec(
    val key: String, val entity: String, val title: String, val noun: String, val viewCaps: List<String>, val manageCaps: List<String>,
    val fields: List<RField>, val line: (JsonObject) -> Pair<String, String>, val amount: (JsonObject) -> String? = { null },
    val tone: (JsonObject) -> String = { it.s("status") }, val extra: (JsonObject) -> List<Pair<String, String>> = { emptyList() },
    val actions: List<RAction> = emptyList(), val editable: (JsonObject) -> Boolean = { true }, val newScreen: Screen? = null,
    val info: String? = null,
)

private val species = listOf("ELEPHANT" to "Elephant", "BUFFALO" to "Buffalo", "LION" to "Lion", "LEOPARD" to "Leopard", "HIPPO" to "Hippopotamus",
    "CROC" to "Crocodile", "SABLE" to "Sable", "KUDU" to "Kudu", "ELAND" to "Eland", "IMPALA" to "Impala", "ZEBRA" to "Zebra", "WATERBUCK" to "Waterbuck",
    "BUSHBUCK" to "Bushbuck", "HYENA" to "Spotted hyena", "BABOON" to "Baboon", "WILDDOG" to "Painted (wild) dog", "OTHER" to "Other")

private fun ward(o: JsonObject) = o.s("ward").ifBlank { "-" }

val REGISTERS: Map<String, RegisterSpec> = listOf(
    RegisterSpec("wildlife", Entities.WILDLIFE, "Wildlife database", "wildlife record", listOf("wildlife.view", "wildlife.manage"), listOf("wildlife.manage"),
        listOf(RField("species", "Species", "choice", species, true),
            RField("record_type", "Record", "choice", listOf("SIGHTING" to "Sighting", "GROUND" to "Ground count / transect", "AERIAL" to "Aerial survey",
                "CAMERA" to "Camera trap", "MORTALITY" to "Mortality (found dead)", "POACHING" to "Poaching case / snare", "PAC" to "Problem animal control")),
            RField("date", "Date (YYYY-MM-DD)", "date", required = true), RField("count", "Number of animals", "int", required = true),
            RField("ward", "Ward", "int"), RField("location", "Location (area, river, village)", required = true), RField("gps", "GPS (lat, long)"),
            RField("notes", "Notes", "multiline")),
        line = { "${it.s("species_label")} × ${it.s("count")}" to "${it.s("reference")} · ${it.s("record_type_label")} · ${prettyDate(it.s("date"))}\n${it.s("location")}, ward ${ward(it)}" },
        tone = { if (it.s("record_type") in listOf("POACHING", "MORTALITY", "PAC")) "URGENT" else "LOCAL" }),
    RegisterSpec("hunting_quotas", Entities.HUNTING_QUOTAS, "Hunting quotas", "quota", listOf("hunts.view", "hunts.manage"), listOf("hunts.manage"),
        listOf(RField("year", "Year", "int", required = true), RField("species", "Species", "choice", species, true), RField("ward", "Ward", "int"),
            RField("concession", "Concession / area"), RField("quota", "Quota (animals)", "int", required = true),
            RField("trophy_fee", "Standard trophy fee (USD)", "number"), RField("notes", "Notes")),
        line = { "${it.s("year")} ${it.s("species_label")} – ${it.s("concession").ifBlank { "ward " + ward(it) }}" to
            "Quota ${it.s("quota")} · used ${it.s("used")} · left ${it.s("remaining")} · fee $${money(it.s("trophy_fee"))}" },
        tone = { if (it.s("remaining") == "0") "WAITING" else "ACTIVE" }),
    RegisterSpec("trophy_hunts", Entities.TROPHY_HUNTS, "Trophy hunts (CAMPFIRE)", "hunt", listOf("hunts.view", "hunts.manage"), listOf("hunts.manage"),
        emptyList(),
        line = { "${it.s("species_label")} – ${it.s("client_name")}" to "${it.s("reference")} · ${it.s("operator_name")} · ward ${ward(it)}\n${prettyDate(it.s("hunt_date"))} · PH ${it.s("professional_hunter")}" },
        amount = { "$" + money(it.s("trophy_fee")) },
        extra = { listOf("Species" to it.s("species_label"), "Safari operator" to it.s("operator_name"), "Professional hunter" to it.s("professional_hunter"),
            "Client" to "${it.s("client_name")} (${it.s("client_nationality")})", "Hunt date" to prettyDate(it.s("hunt_date")), "Ward" to ward(it),
            "Trophy" to it.s("trophy_details"), "Trophy fee" to "USD ${money(it.s("trophy_fee"))}",
            "Community (ward) share" to "USD ${money(it.s("community_share"))} (${it.s("community_share_pct")}%)",
            "Council share" to "USD ${money(it.s("council_share"))}") },
        actions = listOf(RAction("Record the hunt", "hunt.action", "hunt", listOf("hunted" to "Animal taken – bill the trophy fee", "cancel" to "Cancel booking"),
            listOf(FieldSpec("hunt_date", "Hunt date (YYYY-MM-DD)"), FieldSpec("trophy_details", "Trophy (sex, size, tusk weight …)")),
            listOf("hunts.manage")) { o, _ -> o.s("status") == "BOOKED" }),
        editable = { false }, newScreen = Screen.NewHunt,
        info = "Trophy fees are billed to the safari operator when the animal is taken and the hunt shows PAID as soon as the fee is received. " +
            "The ward's CAMPFIRE share is worked out on every hunt."),
    RegisterSpec("resource_permits", Entities.RESOURCE_PERMITS, "Sand, mining & forestry permits", "permit application",
        listOf("permits.view", "permits.manage"), listOf("permits.manage"),
        listOf(RField("permit_type", "Type", "choice", listOf("SAND" to "Sand extraction", "GRAVEL" to "Gravel / quarry stone", "CLAY" to "Clay / brick moulding",
            "MINING" to "Small-scale / artisanal mining", "TIMBER" to "Timber harvesting (forestry)", "FIREWOOD" to "Firewood / charcoal",
            "THATCH" to "Thatch grass & reeds", "OTHER" to "Other"), true),
            RField("holder", "Permit holder (council account)", "account", required = true), RField("ward", "Ward", "int"),
            RField("location", "Site (river bed, pit, forest block)", required = true), RField("gps", "GPS (lat, long)"),
            RField("unit", "Unit", "choice", listOf("M3" to "cubic metres", "T" to "tonnes", "LOAD" to "truck loads", "CORD" to "cords / stacks",
                "BUNDLE" to "bundles", "MONTH" to "months")),
            RField("quantity_allowed", "Quantity allowed", "number", required = true), RField("unit_fee", "Fee per unit (USD)", "number", required = true),
            RField("valid_from", "Valid from (YYYY-MM-DD)", "date", required = true), RField("valid_to", "Valid to (YYYY-MM-DD)", "date", required = true),
            RField("ema_reference", "EMA / Mines / Forestry approval no."), RField("conditions", "Conditions", "multiline")),
        line = { "${it.s("permit_type_label")} – ${it.s("holder_name")}" to "${it.s("reference")} · ${it.s("location")}, ward ${ward(it)}\n" +
            "taken ${money(it.s("quantity_extracted"))} of ${money(it.s("quantity_allowed"))} ${it.s("unit_label")} · to ${prettyDate(it.s("valid_to"))}" },
        amount = { "$" + money(it.s("fee")) },
        extra = { o -> listOf("Permit fee" to "USD ${money(o.s("fee"))}", "Taken so far" to "${money(o.s("quantity_extracted"))} ${o.s("unit_label")}",
            "Left" to "${money(o.s("quantity_left"))} ${o.s("unit_label")}", "Captured by" to o.s("applied_by_name"), "Decided by" to o.s("decided_by_name"),
            "Decision note" to o.s("decision_note")) + o.list("extractions").map { e ->
            "Load ${prettyDate(e.s("date"))}" to "${money(e.s("quantity"))} ${o.s("unit_label")} · ${e.s("vehicle_reg")} → ${e.s("destination")}" } },
        actions = listOf(
            RAction("Decision", "permit.decide", "permit", listOf("approve" to "Approve & bill the fee", "reject" to "Reject"),
                listOf(FieldSpec("unit_fee", "Fee per unit (USD) – blank keeps the applied rate", "number"), FieldSpec("note", "Comment / reason", "multiline")),
                listOf("permits.approve")) { o, c ->
                o.s("status") == "APPLIED" && o.s("applied_by") != c.me.id.toString() },
            RAction("Record a load / quantity taken", "extraction.record", "permit", listOf("record" to "Record"),
                listOf(FieldSpec("quantity", "Quantity", "number"), FieldSpec("vehicle_reg", "Vehicle registration"), FieldSpec("destination", "Destination")),
                listOf("permits.manage")) { o, _ -> o.s("status") == "ACTIVE" },
            RAction("Suspend permit", "permit.decide", "permit", listOf("suspend" to "Suspend"), listOf(FieldSpec("note", "Reason", "multiline")),
                listOf("permits.approve")) { o, _ -> o.s("status") == "ACTIVE" }),
        editable = { it.s("status") == "APPLIED" },
        info = "Approval bills the permit fee (quantity × fee per unit); the permit becomes ACTIVE as soon as it is paid. Loads are checked against the " +
            "permitted quantity – going over it is refused (issue a fine)."),
    RegisterSpec("farms", Entities.FARMS, "Agricultural farms", "farm", listOf("farms.view", "farms.manage"), listOf("farms.manage"),
        listOf(RField("name", "Farm name", required = true), RField("owner", "Owner / occupier (council account)", "account", required = true),
            RField("farm_number", "Farm / plot number", required = true), RField("ward", "Ward", "int"),
            RField("location", "Area / resettlement scheme", required = true), RField("hectares", "Hectares", "number", required = true),
            RField("farm_type", "Type", "choice", listOf("A1" to "A1 resettlement", "A2" to "A2 commercial", "COMMUNAL" to "Communal land",
                "SSCF" to "Small-scale commercial", "LSCF" to "Large-scale commercial", "ESTATE" to "Estate / plantation", "IRRIG" to "Irrigation scheme plot")),
            RField("activity", "Main activity", "choice", listOf("MIXED" to "Mixed farming", "CROPS" to "Crops", "LIVESTOCK" to "Livestock",
                "HORT" to "Horticulture", "PLANT" to "Tea / coffee / timber plantation", "DAIRY" to "Dairy", "POULTRY" to "Poultry")),
            RField("main_crops", "Main crops"), RField("cattle", "Cattle", "int"), RField("goats_sheep", "Goats / sheep", "int"),
            RField("irrigated_hectares", "Irrigated hectares", "number"), RField("water_source", "Water source"), RField("gps", "GPS (lat, long)"),
            RField("status", "Status", "choice", listOf("ACTIVE" to "Active", "IDLE" to "Idle / under-used", "DISPUTED" to "Boundary / ownership dispute",
                "ABANDONED" to "Abandoned")), RField("notes", "Notes", "multiline")),
        line = { "${it.s("name")} (${it.s("hectares")} ha)" to "${it.s("reference")} · ${it.s("owner_name")} · ${it.s("farm_type_label")}\n${it.s("location")}, ward ${ward(it)} · ${it.s("main_crops")}" },
        info = "Every farm is billed the farm levy per hectare in the yearly levy run."),
    RegisterSpec("water_points", Entities.WATER_POINTS, "Water points (WASH)", "water point", listOf("water.view", "water.manage"), listOf("water.manage"),
        listOf(RField("name", "Name", required = true), RField("point_type", "Type", "choice", listOf("BOREHOLE" to "Borehole (bush pump)",
            "SOLAR" to "Solar-powered borehole", "WELL" to "Protected well", "PIPED" to "Piped water scheme", "SPRING" to "Protected spring", "DAM" to "Dam / weir")),
            RField("ward", "Ward", "int"), RField("village", "Village", required = true), RField("households_served", "Households served", "int"),
            RField("status", "Status", "choice", listOf("WORKING" to "Working", "BROKEN" to "Broken down", "REPAIR" to "Under repair", "DRY" to "Dry / low yield",
                "DECOM" to "Decommissioned")), RField("last_serviced", "Last serviced (YYYY-MM-DD)", "date"),
            RField("water_quality_ok", "Last water test passed", "bool"), RField("committee_contact", "Water committee contact"), RField("gps", "GPS"),
            RField("notes", "Faults / repairs", "multiline")),
        line = { it.s("name") to "${it.s("reference")} · ${it.s("point_type_label")} · ${it.s("village")}, ward ${ward(it)}\n${it.s("households_served")} households · serviced ${prettyDate(it.s("last_serviced"))}" },
        tone = { when (it.s("status")) { "WORKING" -> "ACTIVE"; "BROKEN", "DECOM" -> "BROKEN"; else -> "IN_PROGRESS" } }),
    RegisterSpec("fines", Entities.FINES, "Fines & penalties", "fine", listOf("fines.view", "fines.issue"), listOf("fines.issue"), emptyList(),
        line = { "${it.s("offender_name")} – ${it.s("offence_name").substringBefore(" (")}" to "${it.s("reference")} · ${prettyDate(it.s("date"))} · ${it.s("location")}\nIssued by ${it.s("issued_by_name")}" },
        amount = { "$" + money(it.s("amount")) },
        tone = { when (it.s("status")) { "ISSUED" -> "UNPAID"; "COURT" -> "URGENT"; "WAIVED" -> "WAITING"; else -> it.s("status") } },
        extra = { listOf("Offence" to it.s("offence_name"), "Offender" to it.s("offender_name"), "ID" to it.s("national_id"), "Phone" to it.s("phone"),
            "Vehicle" to it.s("vehicle_reg"), "Where" to "${it.s("location")}, ward ${ward(it)}", "Date" to prettyDate(it.s("date")),
            "Amount" to "USD ${money(it.s("amount"))}", "Issued by" to it.s("issued_by_name"), "Decision" to it.s("decision_reason")) },
        actions = listOf(
            RAction("Waive the fine (Treasurer / CEO)", "fine.decide", "fine", listOf("waive" to "Waive"), listOf(FieldSpec("reason", "Reason", "multiline")),
                listOf("fines.waive")) { o, c -> o.s("status") == "ISSUED" && o.s("issued_by") != c.me.id.toString() },
            RAction("Not paid?", "fine.decide", "fine", listOf("court" to "Refer to court"), listOf(FieldSpec("reason", "Note", "multiline")),
                listOf("fines.issue", "fines.waive")) { o, _ -> o.s("status") == "ISSUED" }),
        editable = { false }, newScreen = Screen.NewFine,
        info = "A fine is billed to the offender's council account (opened from the ID or phone if needed), sent by SMS, and shows PAID as soon as it is paid."),
    // ---------------------------------------------------------------- Technical Services
    RegisterSpec("roads", Entities.ROADS, "Road network", "road", listOf("roads.view", "roads.manage"), listOf("roads.manage"),
        listOf(RField("name", "Road name", required = true), RField("road_number", "District road number"), RField("ward", "Ward", "int"),
            RField("start_point", "From", required = true), RField("end_point", "To", required = true), RField("length_km", "Length (km)", "number", required = true),
            RField("surface", "Surface", "choice", listOf("GRAVEL" to "Gravel", "TAR" to "Tarred / bitumen", "EARTH" to "Earth / track", "CONCRETE" to "Concrete strip")),
            RField("condition", "Condition", "choice", listOf("FAIR" to "Fair", "GOOD" to "Good", "POOR" to "Poor – needs rehabilitation", "IMPASSABLE" to "Impassable")),
            RField("last_graded", "Last graded (YYYY-MM-DD)", "date"), RField("bridges_culverts", "Bridges / culverts", "int"), RField("notes", "Notes", "multiline")),
        line = { "${it.s("name")} (${it.s("length_km")} km)" to "${it.s("reference")} · ${it.s("road_number")} · ${it.s("surface_label")} · ward ${ward(it)}\nLast graded ${prettyDate(it.s("last_graded"))}" },
        tone = { when (it.s("condition")) { "GOOD" -> "ACTIVE"; "FAIR" -> "IN_PROGRESS"; else -> "BROKEN" } },
        extra = { listOf("Condition" to it.s("condition_label")) }),
    RegisterSpec("public_lights", Entities.PUBLIC_LIGHTS, "Public lighting", "light", listOf("lighting.view", "lighting.manage"), listOf("lighting.manage"),
        listOf(RField("light_type", "Type", "choice", listOf("STREET" to "Street light", "HIGHMAST" to "High-mast light", "SOLAR" to "Solar street light", "FLOOD" to "Flood light")),
            RField("location", "Location", required = true), RField("ward", "Ward", "int"), RField("pole_number", "Pole number"),
            RField("status", "Status", "choice", listOf("WORKING" to "Working", "FAULTY" to "Faulty / not lighting", "VANDAL" to "Vandalised / stolen parts", "REPAIR" to "Under repair")),
            RField("last_checked", "Last checked (YYYY-MM-DD)", "date"), RField("notes", "Notes", "multiline")),
        line = { "${it.s("light_type_label")} – ${it.s("location")}" to "${it.s("reference")} · pole ${it.s("pole_number")} · ward ${ward(it)} · checked ${prettyDate(it.s("last_checked"))}" },
        tone = { when (it.s("status")) { "WORKING" -> "ACTIVE"; "REPAIR" -> "IN_PROGRESS"; else -> "BROKEN" } }),
    RegisterSpec("work_orders", Entities.WORK_ORDERS, "Engineering work orders", "work order", listOf("works.view", "works.manage"), listOf("works.manage"),
        listOf(RField("kind", "Type", "choice", listOf("ROAD" to "Road maintenance / grading / patching", "DRAIN" to "Drainage / culverts", "LIGHT" to "Public lighting repair",
            "BUILDING" to "Council building maintenance", "PLANT" to "Plant & vehicle repair", "WATER" to "Water / borehole repair", "OTHER" to "Other engineering work")),
            RField("title", "Work to be done", required = true), RField("location", "Location", required = true), RField("ward", "Ward", "int"),
            RField("description", "Details", "multiline"), RField("assigned_to", "Give the job to", "staff"), RField("due_date", "Due (YYYY-MM-DD)", "date")),
        line = { it.s("title") to "${it.s("reference")} · ${it.s("kind_label")} · ${it.s("location")}\n${it.s("assigned_to_name").ifBlank { "not assigned" }} · due ${prettyDate(it.s("due_date"))}" },
        amount = { if (it.s("cost") !in listOf("", "0", "0.00")) "$" + money(it.s("cost")) else null },
        tone = { when (it.s("status")) { "CLOSED" -> "CLOSED"; "DONE" -> "VERIFIED"; "IN_PROGRESS" -> "IN_PROGRESS"; else -> "OPEN" } },
        extra = { listOf("Assigned to" to it.s("assigned_to_name"), "Road" to it.s("road_name"), "Light" to it.s("light_name"), "Materials" to it.s("materials"),
            "Labour (days)" to it.s("labour_days"), "Cost" to "USD ${money(it.s("cost"))}", "Completion notes" to it.s("completion_notes"),
            "Signed off by" to it.s("signed_off_by_name")) },
        actions = listOf(
            RAction("Report progress", "work.action", "work_order", listOf("done" to "Work done", "start" to "Started"),
                listOf(FieldSpec("notes", "What was done", "multiline"), FieldSpec("materials", "Materials used"), FieldSpec("labour_days", "Labour (days)", "number"),
                    FieldSpec("cost", "Cost (USD)", "number")), listOf("works.manage", "works.view", "tasks.view")) { o, c ->
                o.s("status") in listOf("OPEN", "IN_PROGRESS") && (o.s("assigned_to") == c.me.id.toString() || c.me.can("works.assign")) },
            RAction("Sign off (District Engineer)", "work.action", "work_order", listOf("signoff" to "Sign off", "reopen" to "Send back"),
                listOf(FieldSpec("notes", "Comment", "multiline")), listOf("works.assign")) { o, c -> o.s("status") == "DONE" && o.s("assigned_to") != c.me.id.toString() }),
        editable = { it.s("status") == "OPEN" },
        info = "The District Engineer assigns job cards; the officer reports the work, materials and cost; the Engineer signs it off (a repaired light shows Working, a graded road gets today's date)."),
    // ---------------------------------------------------------------- Administration
    RegisterSpec("record_files", Entities.RECORD_FILES, "Records management (registry)", "file", listOf("records.view", "records.manage"), listOf("records.manage"),
        listOf(RField("file_number", "File number", required = true), RField("title", "Title", required = true),
            RField("department", "Department", "choice", listOf("ADMIN" to "Administration", "FINANCE" to "Finance", "SOCIAL" to "Social Services",
                "TECH" to "Technical Services", "AUDIT" to "Internal Audit", "EXEC" to "Office of the CEO", "GROWTH" to "Growth Points")),
            RField("category", "Category"), RField("location", "Cabinet / shelf / box", required = true), RField("confidential", "Confidential", "bool"),
            RField("opened_on", "Opened (YYYY-MM-DD)", "date"), RField("retain_until", "Keep until (YYYY-MM-DD)", "date"), RField("notes", "Notes", "multiline")),
        line = { "${it.s("file_number")} – ${it.s("title")}" to "${it.s("department_label")} · ${it.s("location")}" +
            (if (it.s("status") == "LOAN") "\nWith ${it.s("borrowed_by_name")} – due ${prettyDate(it.s("due_back"))}" else "") },
        tone = { when (it.s("status")) { "IN" -> "ACTIVE"; "LOAN" -> "IN_PROGRESS"; else -> "WAITING" } },
        extra = { listOf("With" to it.s("borrowed_by_name"), "Due back" to prettyDate(it.s("due_back"))) },
        actions = listOf(
            RAction("File returned?", "record.action", "record_file", listOf("return" to "Returned to the registry"), emptyList(), listOf("records.manage")) { o, _ -> o.s("status") == "LOAN" },
            RAction("Archive", "record.action", "record_file", listOf("archive" to "Archive the file"), emptyList(), listOf("records.manage")) { o, _ -> o.s("status") == "IN" })),
    // ---------------------------------------------------------------- Social Services – public health & community
    RegisterSpec("health_inspections", Entities.HEALTH_INSPECTIONS, "Public health inspections", "inspection", listOf("health.view", "health.manage"), listOf("health.manage"),
        listOf(RField("premises", "Premises", required = true), RField("premises_type", "Type", "choice", listOf("FOOD" to "Food outlet / restaurant", "BUTCHERY" to "Butchery",
            "MARKET" to "Market", "ABATTOIR" to "Abattoir / slaughter slab", "SCHOOL" to "School", "INST" to "Clinic / institution", "LODGE" to "Lodge / guest house", "OTHER" to "Other premises")),
            RField("owner", "Owner / operator"), RField("ward", "Ward", "int"), RField("location", "Location", required = true),
            RField("date", "Date (YYYY-MM-DD)", "date", required = true), RField("score", "Score (out of 100)", "int"),
            RField("result", "Result", "choice", listOf("PASS" to "Passed", "FOLLOWUP" to "Passed – follow-up needed", "FAIL" to "Failed – closure / notice served")),
            RField("findings", "Findings and corrections needed", "multiline", required = true), RField("follow_up_date", "Follow-up visit (YYYY-MM-DD)", "date")),
        line = { it.s("premises") to "${it.s("reference")} · ${it.s("premises_type_label")} · ${prettyDate(it.s("date"))}\n${it.s("location")}, ward ${ward(it)} · score ${it.s("score").ifBlank { "-" }}" },
        tone = { when (it.s("result")) { "PASS" -> "ACTIVE"; "FAIL" -> "BROKEN"; else -> "IN_PROGRESS" } },
        extra = { listOf("Result" to it.s("result_label"), "Inspector" to it.s("inspector_name")) }),
    RegisterSpec("sanitation", Entities.SANITATION, "Ablutions & waste management", "facility", listOf("sanitation.view", "sanitation.manage"), listOf("sanitation.manage"),
        listOf(RField("name", "Name", required = true), RField("kind", "Type", "choice", listOf("ABLUTION" to "Public ablution block", "REFUSE" to "Refuse collection point / skip",
            "DUMPSITE" to "Dumpsite / landfill", "BLAIR" to "Blair / VIP toilet (institution)")), RField("ward", "Ward", "int"), RField("location", "Location", required = true),
            RField("status", "Status", "choice", listOf("GOOD" to "Clean / working", "NEEDS" to "Needs cleaning / collection", "BLOCKED" to "Blocked / full / broken", "CLOSED" to "Closed")),
            RField("last_serviced", "Last cleaned / collected (YYYY-MM-DD)", "date"), RField("collection_days", "Collection days"), RField("caretaker", "Caretaker"),
            RField("notes", "Notes", "multiline")),
        line = { it.s("name") to "${it.s("reference")} · ${it.s("kind_label")} · ${it.s("location")}\nServiced ${prettyDate(it.s("last_serviced"))} ${it.s("collection_days")}" },
        tone = { when (it.s("status")) { "GOOD" -> "ACTIVE"; "NEEDS" -> "IN_PROGRESS"; else -> "BROKEN" } }),
    RegisterSpec("social_facilities", Entities.SOCIAL_FACILITIES, "Schools & clinics development", "school / clinic", listOf("facilities.view", "facilities.manage"),
        listOf("facilities.manage"),
        listOf(RField("name", "Name", required = true), RField("kind", "Type", "choice", listOf("PRIMARY" to "Primary school", "SECONDARY" to "Secondary school", "ECD" to "ECD centre",
            "CLINIC" to "Clinic", "HOSPITAL" to "Hospital", "HALL" to "Community hall / centre")), RField("ward", "Ward", "int"), RField("location", "Location", required = true),
            RField("responsible_authority", "Responsible authority"), RField("population_served", "Learners / population served", "int"),
            RField("classrooms_or_beds", "Classrooms / beds", "int"),
            RField("condition", "Condition", "choice", listOf("FAIR" to "Fair", "GOOD" to "Good", "POOR" to "Poor", "BUILDING" to "Under construction / upgrade")),
            RField("needs", "Development needs", "multiline"), RField("contact", "Contact (head / sister-in-charge)")),
        line = { it.s("name") to "${it.s("reference")} · ${it.s("kind_label")} · ward ${ward(it)} · ${it.s("population_served")} served\n${it.s("needs")}" },
        tone = { when (it.s("condition")) { "GOOD" -> "ACTIVE"; "POOR" -> "BROKEN"; else -> "IN_PROGRESS" } },
        extra = { listOf("Condition" to it.s("condition_label")) }),
    // ---------------------------------------------------------------- Administration – land, liaison, notices
    RegisterSpec("land_parcels", Entities.LAND_PARCELS, "Council land bank", "land parcel", listOf("land.view", "land.manage"), listOf("land.manage"),
        listOf(RField("parcel_number", "Parcel number", required = true), RField("name", "Name", required = true), RField("ward", "Ward", "int"),
            RField("location", "Location", required = true), RField("hectares", "Hectares", "number", required = true),
            RField("land_use", "Use", "choice", listOf("RES" to "Residential", "COM" to "Commercial", "IND" to "Industrial", "INST" to "Institutional",
                "AGR" to "Agricultural", "OPEN" to "Open space / recreation", "MIXED" to "Mixed use")),
            RField("status", "Status", "choice", listOf("VACANT" to "Vacant – available", "PLANNED" to "Planned / being surveyed", "ALLOCATED" to "Allocated / sold",
                "LEASED" to "Leased", "RESERVED" to "Reserved for council use", "ENCROACHED" to "Encroached / disputed")),
            RField("survey_diagram", "Survey diagram / plan no."), RField("title_deed", "Title deed"), RField("valuation", "Valuation (USD)", "number"),
            RField("stands_planned", "Stands planned", "int"), RField("notes", "Notes", "multiline")),
        line = { "${it.s("parcel_number")} – ${it.s("name")}" to "${it.s("land_use_label")} · ${it.s("hectares")} ha · ${it.s("location")}, ward ${ward(it)}" +
            (if (it.s("stands_planned") !in listOf("", "0")) "\n${it.s("stands_planned")} stands planned" else "") },
        tone = { when (it.s("status")) { "VACANT" -> "ACTIVE"; "ENCROACHED" -> "BROKEN"; "PLANNED" -> "IN_PROGRESS"; else -> "WAITING" } }),
    RegisterSpec("engagements", Entities.ENGAGEMENTS, "Stakeholder engagement", "meeting", listOf("engagements.view", "engagements.manage"),
        listOf("engagements.manage"),
        listOf(RField("title", "Meeting", required = true), RField("kind", "Type", "choice", listOf("WARD" to "Ward development committee (WADCO)",
            "VILLAGE" to "Village assembly / VIDCO", "BUDGET" to "Budget consultation", "TRAD" to "Traditional leaders", "PARTNER" to "Development partner / NGO",
            "BUSINESS" to "Business community", "MEDIA" to "Media / public relations")), RField("date", "Date (YYYY-MM-DD)", "date", required = true),
            RField("ward", "Ward", "int"), RField("venue", "Venue", required = true), RField("attendance", "Attendance", "int"),
            RField("issues_raised", "Issues raised", "multiline"), RField("resolutions", "Agreed actions", "multiline"),
            RField("status", "Status", "choice", listOf("PLANNED" to "Planned", "HELD" to "Held – report written", "FOLLOWUP" to "Held – follow-up actions open",
                "CANCELLED" to "Cancelled"))),
        line = { it.s("title") to "${it.s("reference")} · ${it.s("kind_label")} · ${prettyDate(it.s("date"))} · ${it.s("venue")}" +
            (if (it.s("attendance") !in listOf("", "0")) " · ${it.s("attendance")} people" else "") },
        tone = { when (it.s("status")) { "HELD" -> "ACTIVE"; "FOLLOWUP" -> "IN_PROGRESS"; "CANCELLED" -> "CANCELLED"; else -> "WAITING" } }),
    RegisterSpec("public_notices", Entities.PUBLIC_NOTICES, "Public notices to residents", "notice", listOf("notices.view", "notices.manage"),
        listOf("notices.manage"),
        listOf(RField("title", "Title", required = true), RField("category", "Type", "choice", listOf("GENERAL" to "General notice", "MEETING" to "Public meeting / consultation",
            "WATER" to "Water / service interruption", "DEADLINE" to "Payment / licence deadline", "TENDER" to "Tender / vacancy", "HEALTH" to "Health alert",
            "EMERGENCY" to "Emergency / disaster")), RField("body", "Notice", "multiline", required = true), RField("ward", "Ward (blank = whole district)", "int"),
            RField("publish_from", "Publish from (YYYY-MM-DD)", "date"), RField("expires_on", "Until (YYYY-MM-DD)", "date"),
            RField("is_published", "Show in the residents' app", "bool")),
        line = { it.s("title") to "${it.s("category_label")} · ${it.s("ward").takeIf { w -> w.isNotBlank() }?.let { w -> "ward $w" } ?: "whole district"} · until ${prettyDate(it.s("expires_on"))}\n${it.s("body")}" },
        tone = { if (it.s("is_published") == "true") "ACTIVE" else "WAITING" },
        info = "Published notices appear on the home screen of the residents' app (filtered by ward when one is given)."),
    // ---------------------------------------------------------------- Internal audit
    RegisterSpec("audit_engagements", Entities.AUDIT_ENGAGEMENTS, "Internal audit plan", "audit", listOf("auditplan.view", "auditplan.manage"),
        listOf("auditplan.manage"),
        listOf(RField("title", "Audit", required = true), RField("audit_type", "Type", "choice", listOf("COMP" to "Compliance audit", "FIN" to "Financial audit",
            "PERF" to "Performance / value for money", "SYS" to "Systems / ICT review", "SPECIAL" to "Special investigation", "STOCK" to "Stores / asset verification")),
            RField("department", "Department audited", "choice", listOf("ADMIN" to "Administration", "FINANCE" to "Finance", "SOCIAL" to "Social Services", "TECH" to "Technical Services", "AUDIT" to "Internal Audit", "EXEC" to "Office of the CEO", "GROWTH" to "Growth Points")), RField("quarter", "Quarter (e.g. 2026-Q4)", required = true),
            RField("auditor", "Auditor", "staff"), RField("status", "Status", "choice", listOf("PLANNED" to "Planned", "FIELDWORK" to "Fieldwork",
                "REPORTING" to "Draft report", "DONE" to "Final report issued")), RField("scope", "Scope", "multiline"), RField("conclusion", "Conclusion", "multiline")),
        line = { it.s("title") to "${it.s("reference")} · ${it.s("quarter")} · ${it.s("department_label")} · ${it.s("audit_type_label")}\n${it.s("auditor_name")}" },
        tone = { when (it.s("status")) { "DONE" -> "CLOSED"; "PLANNED" -> "WAITING"; else -> "IN_PROGRESS" } }),
).associateBy { it.key }

private fun canSee(ctx: Ctx, spec: RegisterSpec) = ctx.me.can(*spec.viewCaps.toTypedArray())
private fun canManage(ctx: Ctx, spec: RegisterSpec) = ctx.me.can(*spec.manageCaps.toTypedArray())

@Composable
fun RegisterListScreen(ctx: Ctx, key: String) {
    val spec = REGISTERS.getValue(key)
    val all by ctx.sdk.observe(spec.entity, JsonObject.serializer()).collectAsState(initial = emptyList())
    var q by remember { mutableStateOf("") }
    val list = all.filter { q.isBlank() || it.toString().contains(q, ignoreCase = true) }
    AppScreen(spec.title, onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        if (canManage(ctx, spec)) PrimaryButton("+ New ${spec.noun}", onClick = { ctx.go(spec.newScreen ?: Screen.RegisterForm(key, null)) })
        ListScreen {
            item { Field("Search", q, { q = it }) }
            if (key == "farms" && all.isNotEmpty()) item {
                val ha = all.sumOf { it.s("hectares").toDoubleOrNull() ?: 0.0 }
                InfoBox("${all.size} farms · ${money(ha.toString()).removeSuffix(".00")} ha · ${all.sumOf { it.s("cattle").toIntOrNull() ?: 0 }} cattle")
            }
            if (list.isEmpty()) item { Empty("Nothing here yet.") }
            items(list, key = { it.s("id") }) { o ->
                val (t, sub) = spec.line(o)
                val status = o.s("status_label").ifBlank { if (key == "beneficiaries") (if (o.s("is_active") == "true") "Active" else "Closed") else "" }
                RowCard(t, sub, spec.amount(o), status.ifBlank { null }, spec.tone(o), o.s("local_note").ifBlank { null }) {
                    ctx.go(Screen.RegisterItem(key, o.s("id")))
                }
            }
        }
    }
}

@Composable
fun RegisterItemScreen(ctx: Ctx, key: String, id: String) {
    val spec = REGISTERS.getValue(key)
    val item by ctx.sdk.observeOne(spec.entity, id, JsonObject.serializer()).collectAsState(initial = null)
    AppScreen(spec.title, onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        val o = item ?: return@AppScreen Empty("Not found")
        ScrollColumn {
            val (t, _) = spec.line(o)
            SectionCard(listOf(o.s("reference"), t).filter { it.isNotBlank() }.joinToString(" – ")) {
                spec.fields.forEach { f ->
                    val v = when (f.kind) {
                        "choice" -> o.s(f.key + "_label").ifBlank { o.s(f.key) }
                        "account", "ref", "staff" -> o.s(f.key + "_name")
                        "bool" -> if (o.s(f.key) == "true") "Yes" else "No"
                        "date" -> prettyDate(o.s(f.key))
                        else -> o.s(f.key)
                    }
                    KeyValue(f.label.substringBefore(" ("), v)
                }
                spec.extra(o).forEach { (k, v) -> KeyValue(k, v) }
                if (o.s("status_label").isNotBlank()) Row { StatusChip(o.s("status_label"), spec.tone(o)) }
                o.s("local_note").takeIf { it.isNotBlank() }?.let { InfoBox(it) }
            }
            spec.info?.let { InfoBox(it) }
            spec.actions.filter { ctx.me.can(*it.caps.toTypedArray()) && it.visible(o, ctx) }.forEach { a ->
                ActionPanel(a.title, a.fields, a.buttons) { action, values ->
                    ctx.sdk.markPending(spec.entity, id, "${a.title} – queued")
                    ctx.sdk.enqueue(a.op, "${spec.title}: ${o.s("reference")} $action", spec.entity, id) {
                        put(a.idKey, id); put("action", action)
                        values.forEach { (k, v) -> if (v.isNotBlank()) put(k, v) }
                        if (a.op == "extraction.record" || a.op == "assistance.give") put("id", ctx.sdk.newId())
                    }
                }
            }
            if (canManage(ctx, spec) && spec.fields.isNotEmpty() && spec.editable(o)) SecondaryButton("Edit", { ctx.go(Screen.RegisterForm(key, id)) })
        }
    }
}

@Composable
private fun AccountField(ctx: Ctx, label: String, selectedId: String, selectedName: String, onPick: (ClientAccount) -> Unit) {
    var q by remember { mutableStateOf("") }
    val accounts by ctx.sdk.search(Entities.ACCOUNTS, q, ClientAccount.serializer()).collectAsState(initial = emptyList())
    Field("$label – search", q, { q = it })
    Picker(label, accounts.take(30), accounts.firstOrNull { it.id == selectedId }, { "${it.accountNumber} – ${it.name}" }, onPick)
    if (selectedName.isNotBlank()) Text("Selected: $selectedName", fontSize = 12.sp, color = CrdcColors.Muted)
}

@Composable
fun RegisterFormScreen(ctx: Ctx, key: String, id: String?) {
    val spec = REGISTERS.getValue(key)
    val existing by (if (id != null) ctx.sdk.observeOne(spec.entity, id, JsonObject.serializer())
                     else kotlinx.coroutines.flow.flowOf(null)).collectAsState(initial = null)
    val values = remember(id, existing != null) {
        mutableStateMapOf<String, String>().apply {
            spec.fields.forEach { f ->
                put(f.key, existing?.s(f.key) ?: when {
                    f.kind == "choice" -> f.choices.first().first
                    f.kind == "bool" -> "true"
                    f.key == "year" -> ctx.sdk.nowIso().take(4)
                    else -> ""
                })
                existing?.s(f.key + "_name")?.let { put(f.key + "_name", it) }
            }
        }
    }
    val missing = spec.fields.filter { it.required && values[it.key].isNullOrBlank() }
    AppScreen(if (id == null) "New ${spec.noun}" else "Edit ${spec.noun}", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            spec.fields.forEach { f ->
                when (f.kind) {
                    "choice" -> ChoicePicker(f.label, f.choices, values[f.key] ?: "") { values[f.key] = it }
                    "bool" -> ChoicePicker(f.label, listOf("true" to "Yes", "false" to "No"), values[f.key] ?: "true") { values[f.key] = it }
                    "multiline" -> Field(f.label, values[f.key] ?: "", { values[f.key] = it }, singleLine = false, minLines = 3)
                    "number", "int" -> Field(f.label + if (f.required) " *" else "", values[f.key] ?: "", { values[f.key] = it }, number = true)
                    "account" -> AccountField(ctx, f.label, values[f.key] ?: "", values[f.key + "_name"] ?: "") {
                        values[f.key] = it.id; values[f.key + "_name"] = it.name
                    }
                    "staff" -> {
                        val staff by ctx.sdk.observe(Entities.STAFF, StaffMember.serializer()).collectAsState(initial = emptyList())
                        val mine = staff.filter { it.isActive && it.department == ctx.me.department }
                        Picker(f.label, mine, mine.firstOrNull { it.userId.toString() == values[f.key] }, { "${it.fullName} – ${it.roleLabel}" }, onSelect = {
                            values[f.key] = it.userId.toString(); values[f.key + "_name"] = it.fullName
                        })
                    }
                    else -> Field(f.label + if (f.required) " *" else "", values[f.key] ?: "", { values[f.key] = it })
                }
            }
            if (missing.isNotEmpty()) Text("Still needed: " + missing.joinToString { it.label.substringBefore(" (") }, fontSize = 12.sp, color = CrdcColors.Warning)
            PrimaryButton("Save", enabled = missing.isEmpty(), onClick = {
                val rid = id ?: ctx.sdk.newId()
                val now = ctx.sdk.nowIso()
                val optimistic = buildJsonObject {
                    (existing ?: JsonObject(emptyMap())).forEach { (k, v) -> put(k, v) }
                    put("id", rid); put("updated_at", now); if (id == null) put("reference", "(pending)")
                    spec.fields.forEach { f ->
                        put(f.key, values[f.key] ?: "")
                        if (f.kind == "choice") put(f.key + "_label", f.choices.firstOrNull { it.first == values[f.key] }?.second ?: "")
                        if (f.kind == "account" || f.kind == "staff") put(f.key + "_name", values[f.key + "_name"] ?: "")
                    }
                    put("local_note", "Saved on this device – sent on sync")
                }
                ctx.sdk.enqueue("register.save", "${spec.title}: ${values[spec.fields.first().key]}", spec.entity, rid, optimistic) {
                    put("register", key); put("id", rid)
                    put("fields", buildJsonObject {
                        spec.fields.forEach { f ->
                            val v = values[f.key] ?: ""
                            when {
                                v.isBlank() && f.kind in listOf("int", "number", "date", "account", "staff") -> Unit
                                f.kind == "bool" -> put(f.key, v == "true")
                                else -> put(f.key, v)
                            }
                        }
                    })
                }
                ctx.back()
            })
        }
    }
}

// --------------------------------------------------------- special forms
@Composable
fun NewHuntScreen(ctx: Ctx) {
    val quotas by ctx.sdk.observe(Entities.HUNTING_QUOTAS, JsonObject.serializer()).collectAsState(initial = emptyList())
    var quota by remember { mutableStateOf<JsonObject?>(null) }
    var operatorId by remember { mutableStateOf("") }
    var operatorName by remember { mutableStateOf("") }
    var client by remember { mutableStateOf("") }
    var nationality by remember { mutableStateOf("") }
    var ph by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }
    val open = quotas.filter { (it.s("remaining").toIntOrNull() ?: 0) > 0 }
    AppScreen("Book a trophy hunt", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Picker("Quota (species, ward – left)", open, quota, { "${it.s("year")} ${it.s("species_label")} – ${it.s("concession").ifBlank { "ward " + it.s("ward") }} (${it.s("remaining")} left)" },
                { quota = it; if (fee.isBlank()) fee = it.s("trophy_fee") })
            AccountField(ctx, "Safari operator", operatorId, operatorName) { operatorId = it.id; operatorName = it.name }
            Field("Hunting client *", client, { client = it }); Field("Client nationality", nationality, { nationality = it })
            Field("Professional hunter", ph, { ph = it }); Field("Planned hunt date (YYYY-MM-DD)", date, { date = it })
            Field("Trophy fee (USD)", fee, { fee = it }, number = true)
            PrimaryButton("Book", enabled = quota != null && operatorId.isNotBlank() && client.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val q = quota!!
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("species_label", q.s("species_label")); put("client_name", client)
                    put("operator_name", operatorName); put("trophy_fee", fee); put("ward", q.s("ward")); put("hunt_date", date); put("professional_hunter", ph)
                    put("status", "BOOKED"); put("status_label", "Booked"); put("updated_at", ctx.sdk.nowIso()); put("local_note", "Booked on this device – sent on sync")
                }
                ctx.sdk.enqueue("hunt.book", "Trophy hunt: ${q.s("species_label")} – $client", Entities.TROPHY_HUNTS, id, optimistic) {
                    put("id", id); put("quota", q.s("id")); put("operator", operatorId); put("client_name", client); put("client_nationality", nationality)
                    put("professional_hunter", ph); if (date.isNotBlank()) put("hunt_date", date); if (fee.isNotBlank()) put("trophy_fee", fee)
                }
                ctx.back()
            })
            InfoBox("The quota is checked when the booking reaches the council: a fully-used quota is refused.")
        }
    }
}

@Composable
fun NewFineScreen(ctx: Ctx) {
    val offences by ctx.sdk.observe(Entities.OFFENCES, JsonObject.serializer()).collectAsState(initial = emptyList())
    var offence by remember { mutableStateOf<JsonObject?>(null) }
    var name by remember { mutableStateOf("") }
    var nid by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var reg by remember { mutableStateOf("") }
    var place by remember { mutableStateOf("") }
    var wardNo by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    AppScreen("Issue a fine", onBack = ctx::back, sync = ctx.sync, pending = ctx.pending, onSync = ctx::syncNow) {
        ScrollColumn {
            Picker("Offence", offences.filter { it.s("is_active") == "true" }, offence, { "${it.s("code")} – ${it.s("name")} ($${money(it.s("default_fine"))})" },
                { offence = it; amount = it.s("default_fine") })
            Field("Offender (person or business) *", name, { name = it }); Field("National ID / company reg.", nid, { nid = it })
            Field("Phone (the fine is sent by SMS)", phone, { phone = it }); Field("Vehicle registration", reg, { reg = it })
            Field("Where *", place, { place = it }); Field("Ward", wardNo, { wardNo = it }, number = true)
            Field("Amount (USD)", amount, { amount = it }, number = true); Field("Notes", notes, { notes = it }, singleLine = false, minLines = 2)
            PrimaryButton("Issue fine", color = CrdcColors.Danger, enabled = offence != null && name.isNotBlank() && place.isNotBlank(), onClick = {
                val id = ctx.sdk.newId()
                val o = offence!!
                val optimistic = buildJsonObject {
                    put("id", id); put("reference", "(pending)"); put("offender_name", name); put("offence_name", o.s("name")); put("location", place)
                    put("amount", amount); put("date", ctx.sdk.nowIso().take(10)); put("issued_by", ctx.me.id.toString()); put("issued_by_name", ctx.me.fullName)
                    put("status", "ISSUED"); put("status_label", "Issued – unpaid"); put("updated_at", ctx.sdk.nowIso())
                    put("local_note", "Saved on this device – billed and sent by SMS on sync")
                }
                ctx.sdk.enqueue("fine.issue", "Fine: $name – ${o.s("name")}", Entities.FINES, id, optimistic) {
                    put("id", id); put("offence", o.s("id")); put("offender_name", name); put("national_id", nid); put("phone", phone)
                    put("vehicle_reg", reg); put("location", place); wardNo.toIntOrNull()?.let { put("ward", it) }; put("amount", amount); put("notes", notes)
                }
                ctx.back()
            })
        }
    }
}

/** CAMPFIRE summary for the menu tile: trophy fees and the community share by ward. */
@Composable
fun CampfireSummary(ctx: Ctx) {
    val hunts by ctx.sdk.observe(Entities.TROPHY_HUNTS, JsonObject.serializer()).collectAsState(initial = emptyList())
    val live = hunts.filter { it.s("status") != "CANCELLED" }
    val paid = live.filter { it.s("status") == "PAID" }
    fun sum(l: List<JsonObject>, k: String) = l.sumOf { it.s(k).toDoubleOrNull() ?: 0.0 }.toString()
    Row {
        Kpi("Trophy fees billed", "$${money(sum(live, "trophy_fee"))}", "${live.size} hunt(s)", modifier = androidx.compose.ui.Modifier.weight(1f))
        Kpi("Ward share (paid)", "$${money(sum(paid, "community_share"))}", "${paid.size} paid", CrdcColors.Success, androidx.compose.ui.Modifier.weight(1f))
    }
}
