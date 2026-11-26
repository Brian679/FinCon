package zw.gov.chipingerdc.shared.model

/** Paid / unpaid position of one stand or shop, computed from the phone's database. */
data class ShopStatus(
    val property: Property, val rates: Double, val levies: Double, val rent: Double, val other: Double,
    val licence: String, val lease: Lease?,
) {
    val total get() = rates + levies + rent + other
    val ok get() = total <= 0.005 && licence in listOf("VALID", "N/A")
}

fun shopStatus(p: Property, bills: List<Bill>, licences: List<Licence>, leases: List<Lease>, today: String): ShopStatus {
    val open = bills.filter { it.property == p.id && it.status in listOf("UNPAID", "PART") }
    fun sum(cat: (String) -> Boolean) = open.filter { cat(it.revenueHeadCategory) }.sumOf { it.outstanding.toDoubleOrNull() ?: 0.0 }
    val lic = licences.filter { it.property == p.id }.maxByOrNull { it.createdAt }
    val needs = p.landUse in listOf("COM", "IND") || p.businessName.isNotBlank()
    val licence = when {
        lic == null -> if (needs) "NONE" else "N/A"
        lic.status == "ISSUED" && (lic.expiryDate ?: "") >= today -> "VALID"
        lic.status == "APPROVED" -> "UNPAID"
        lic.status in listOf("APPLIED", "INSPECTION", "INSPECTED") -> "PROCESSING"
        lic.status in listOf("EXPIRED", "ISSUED") -> "EXPIRED"
        else -> "NONE"
    }
    return ShopStatus(p, sum { it == "RATES" }, sum { it == "LEVY" }, sum { it == "RENT" }, sum { it !in listOf("RATES", "LEVY", "RENT") },
        licence, leases.firstOrNull { it.premises == p.id && it.status == "ACTIVE" })
}


/** Words for the licence position, shared by both apps. */
val licenceWords = mapOf("VALID" to "Licence valid", "UNPAID" to "Licence fee not paid", "PROCESSING" to "Licence being processed",
    "EXPIRED" to "Licence expired", "NONE" to "No shop licence", "N/A" to "")

/** Totals for one trading area (growth point, business centre, market …). */
data class AreaTotals(val shops: Int, val paid: Int, val owing: Int, val owed: Double, val noLicence: Int, val notOnApp: Int)

fun areaTotals(rows: List<ShopStatus>) = AreaTotals(rows.size, rows.count { it.ok }, rows.count { !it.ok }, rows.sumOf { it.total },
    rows.count { it.licence in listOf("NONE", "UNPAID", "EXPIRED") }, rows.count { !it.property.registered })
