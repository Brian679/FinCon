package zw.gov.chipingerdc.shared.ui

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

private val months = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

/** "1234.5" -> "1,234.50" */
fun money(value: String?): String {
    val d = value?.toDoubleOrNull() ?: return value ?: "0.00"
    val negative = d < 0
    val cents = kotlin.math.round(kotlin.math.abs(d) * 100).toLong()
    val whole = (cents / 100).toString().reversed().chunked(3).joinToString(",").reversed()
    val frac = (cents % 100).toString().padStart(2, '0')
    return (if (negative) "-" else "") + whole + "." + frac
}

fun money(currency: String, value: String?) = "$currency ${money(value)}"

/** ISO timestamp or date -> "25 Nov 2026 14:05" / "25 Nov 2026". */
fun prettyDate(iso: String?): String {
    if (iso.isNullOrBlank()) return "—"
    return runCatching {
        val dt = Instant.parse(iso).toLocalDateTime(TimeZone.of("Africa/Harare"))
        "${dt.dayOfMonth} ${months[dt.monthNumber - 1]} ${dt.year} ${dt.hour.toString().padStart(2, '0')}:${dt.minute.toString().padStart(2, '0')}"
    }.recoverCatching {
        val d = LocalDate.parse(iso.take(10))
        "${d.dayOfMonth} ${months[d.monthNumber - 1]} ${d.year}"
    }.getOrDefault(iso)
}

fun isPast(iso: String?): Boolean = runCatching { Instant.parse(iso!!) < kotlinx.datetime.Clock.System.now() }.getOrDefault(false)
