package zw.gov.chipingerdc.shared.model

import kotlinx.serialization.Serializable
import kotlin.math.round

@Serializable
data class TaxBandDto(val lower: String = "0", val upper: String? = null, val rate: String = "0")

/** ZIMRA PAYE table synced from the council server (the Treasurer keeps it up to date). */
@Serializable
data class TaxTable(val id: String, val name: String = "", val currency: String = "USD", val effectiveFrom: String = "",
                    val aidsLevyRate: String = "3", val nssaRate: String = "4.5", val nssaCeiling: String = "700", val pensionCap: String = "450",
                    val confirmed: Boolean = false, val source: String = "", val bands: List<TaxBandDto> = emptyList())

data class PayeResult(val nssa: Double, val pensionAllowed: Double, val taxable: Double, val incomeTax: Double, val aidsLevy: Double) {
    val paye get() = incomeTax + aidsLevy
}

private fun r2(v: Double) = round(v * 100) / 100

/** Same rule as the server (payroll/tax.py): tax each slice of taxable income at its band's rate, less credits, plus the AIDS levy. */
fun calculatePaye(t: TaxTable, gross: Double, pension: Double = 0.0, credits: Double = 0.0): PayeResult {
    val nssa = r2(minOf(gross, t.nssaCeiling.toDouble()) * t.nssaRate.toDouble() / 100)
    val pensionAllowed = minOf(pension, t.pensionCap.toDouble())
    val taxable = maxOf(0.0, gross - pensionAllowed - nssa)
    var tax = 0.0
    for (b in t.bands.sortedBy { it.lower.toDouble() }) {
        val lo = b.lower.toDouble()
        if (taxable <= lo) break
        val top = b.upper?.toDoubleOrNull()?.let { minOf(taxable, it) } ?: taxable
        tax += (top - lo) * b.rate.toDouble() / 100
    }
    val incomeTax = maxOf(0.0, r2(tax) - credits)
    return PayeResult(nssa, pensionAllowed, r2(taxable), r2(incomeTax), r2(incomeTax * t.aidsLevyRate.toDouble() / 100))
}

/** The table in force on a date (YYYY-MM-DD) for a currency. */
fun List<TaxTable>.inForce(currency: String, date: String) = filter { it.currency == currency && it.effectiveFrom <= date }.maxByOrNull { it.effectiveFrom }
