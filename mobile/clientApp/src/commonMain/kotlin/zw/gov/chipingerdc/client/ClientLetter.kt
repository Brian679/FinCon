package zw.gov.chipingerdc.client

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import zw.gov.chipingerdc.shared.model.Certificate
import zw.gov.chipingerdc.shared.model.Entities
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.ui.CrdcColors
import zw.gov.chipingerdc.shared.ui.Empty
import zw.gov.chipingerdc.shared.ui.InfoBox
import zw.gov.chipingerdc.shared.ui.PrimaryButton
import zw.gov.chipingerdc.shared.ui.ScrollColumn

private val Ink = Color(0xFF111111)
private val Grey = Color(0xFF555555)
private val Serif = TextStyle(fontFamily = FontFamily.Serif, color = Ink, fontSize = 14.sp, lineHeight = 21.sp)

/** The council crest (same drawing as the website logo). */
@Composable
fun CouncilCrest(modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val k = size.minDimension / 64f
        scale(k, k, pivot = Offset.Zero) {
            val shield = Path().apply {
                moveTo(8f, 6f); lineTo(56f, 6f); lineTo(56f, 36f)
                cubicTo(56f, 50f, 45f, 57f, 32f, 62f)
                cubicTo(19f, 57f, 8f, 50f, 8f, 36f); close()
            }
            drawPath(shield, Color.White)
            drawPath(shield, Color(0xFF2A6DB0), style = Stroke(width = 3f))
            drawCircle(Color(0xFFF2C230), radius = 7f, center = Offset(32f, 18f))
            val tree = Path().apply {
                moveTo(32f, 20f); cubicTo(26f, 20f, 22f, 26f, 22f, 31f); lineTo(42f, 31f); cubicTo(42f, 26f, 38f, 20f, 32f, 20f); close()
            }
            drawPath(tree, Color(0xFF1F7A3A))
            drawRect(Color(0xFF7A3B2E), topLeft = Offset(30f, 29f), size = Size(4f, 9f))
            drawRect(Color(0xFFC0573E), topLeft = Offset(14f, 42f), size = Size(36f, 8f))
            drawLine(Color.White, Offset(14f, 46f), Offset(50f, 46f), strokeWidth = 1f)
        }
    }
}

private fun months(d: String?): String {
    val p = d?.take(10)?.split("-") ?: return ""
    if (p.size < 3) return d
    val m = listOf("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    return "${p[2].trimStart('0')} ${m.getOrElse(p[1].toInt() - 1) { "" }} ${p[0]}"
}

private fun letterBody(x: Certificate): List<AnnotatedString> {
    fun para(build: AnnotatedString.Builder.() -> Unit) = buildAnnotatedString(build)
    fun AnnotatedString.Builder.b(t: String) = withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(t) }
    val council = "Chipinge Rural District Council"
    return when (x.kind) {
        "RESIDENCE" -> listOfNotNull(
            para {
                append("This is to certify that "); b(x.subjectName.ifBlank { x.applicantName }); append(", holder of National Identity Number ")
                b(x.subjectId.ifBlank { x.nationalId }); append(", is a bona fide resident of "); b(x.address)
                x.ward?.let { append(", Ward $it") }; append(", Chipinge District, which falls under the jurisdiction of $council.")
            },
            if (x.purpose.isNotBlank()) para { append("This letter is issued at the request of the above-named person for the purpose of: "); b(x.purpose); append(".") } else null,
            para { append("Any assistance rendered to the above-named person will be greatly appreciated.") },
        )
        "CLEARANCE" -> listOfNotNull(
            para {
                append("This is to certify that all rates, levies and other charges due to $council in respect of "); b(x.propertyLabel)
                append(", account number "); b(x.accountNumber); append(", have been paid in full as at the date of this certificate.")
            },
            if (x.purpose.isNotBlank()) para { append("This certificate is issued for the purpose of: "); b(x.purpose); append(".") } else null,
        )
        "OWNERSHIP" -> listOfNotNull(
            para { append("This is to confirm that "); b(x.propertyLabel); append(" is registered in the records of $council under account number "); b(x.accountNumber); append(".") },
            if (x.purpose.isNotBlank()) para { append("This letter is issued for the purpose of: "); b(x.purpose); append(".") } else null,
        )
        "CESSION" -> listOf(para {
            append("$council has approved the cession (transfer) of "); b(x.propertyLabel); append(" to "); b(x.otherPartyName)
            append(", holder of National Identity Number "); b(x.otherPartyId); append(".")
        })
        "BURIAL" -> listOf(
            para { append("Permission is hereby granted for the burial of the late "); b(x.otherPartyName); append(", who died on "); b(months(x.eventDate)); append(", at "); b(x.place); append(".") },
            para { append("Applicant: ${x.applicantName}, National Identity Number ${x.nationalId}.") },
        )
        else -> emptyList()
    }
}

/** The issued letter, laid out exactly like the printed A4 copy; "Print / save as PDF (A4)" opens that copy. */
@Composable
fun CertificateViewScreen(ctx: CCtx, id: String) {
    val c by ctx.sdk.observeOne(Entities.CERTIFICATES, id, Certificate.serializer()).collectAsState(initial = null)
    val scope = rememberCoroutineScope()
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Letter", onBack = ctx::back) {
        val x = c ?: return@AppScreen Empty("Not found")
        val (title, noun) = when (x.kind) {
            "RESIDENCE" -> "CONFIRMATION OF RESIDENCE" to "letter"; "CLEARANCE" -> "RATES CLEARANCE CERTIFICATE" to "certificate"
            "OWNERSHIP" -> "CONFIRMATION OF STAND OWNERSHIP" to "letter"; "CESSION" -> "APPROVAL OF CESSION (TRANSFER) OF STAND" to "letter"
            "BURIAL" -> "BURIAL ORDER" to "order"; else -> x.kindLabel.uppercase() to "letter"
        }
        val number = x.number.ifBlank { x.reference }
        ScrollColumn {
            Column(Modifier.fillMaxWidth().background(Color.White).border(1.dp, Color(0xFFCCCCCC)).padding(horizontal = 18.dp, vertical = 22.dp)) {
                // letterhead
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CouncilCrest(Modifier.size(52.dp))
                    Column {
                        Text("CHIPINGE RURAL DISTRICT COUNCIL", style = Serif.copy(fontSize = 15.sp, lineHeight = 19.sp, fontWeight = FontWeight.Bold,
                            color = CrdcColors.Green))
                        Text("858 E.D. Mnangagwa Street, P.O. Box 19, Chipinge, Zimbabwe\nTel: +263 227 204 5631-5 · Email: info@chipingerdc.gov.zw\n" +
                            "Facebook: chipingerdc · X: @chipingerdc\nAll correspondence to be addressed to the Chief Executive Officer",
                            style = Serif.copy(fontSize = 9.5.sp, lineHeight = 13.sp, color = Color(0xFF333333)))
                    }
                }
                Spacer(Modifier.height(6.dp))
                Box(Modifier.fillMaxWidth().height(1.dp).background(CrdcColors.Green))
                Spacer(Modifier.height(2.dp))
                Box(Modifier.fillMaxWidth().height(1.dp).background(CrdcColors.Green))
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth()) {
                    Column(Modifier.weight(1f)) {
                        Text(buildAnnotatedString { append("Our ref: "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(number) } }, style = Serif.copy(fontSize = 12.sp))
                        Text("Your ref: ${x.reference}", style = Serif.copy(fontSize = 12.sp))
                    }
                    Text(months(x.decidedAt ?: x.createdAt), style = Serif.copy(fontSize = 12.sp))
                }
                Spacer(Modifier.height(12.dp))
                Text("TO WHOM IT MAY CONCERN", style = Serif)
                Spacer(Modifier.height(14.dp))
                Text(title, Modifier.fillMaxWidth(), style = Serif.copy(fontWeight = FontWeight.Bold, fontSize = 15.sp, textAlign = TextAlign.Center,
                    textDecoration = TextDecoration.Underline))
                Spacer(Modifier.height(12.dp))
                letterBody(x).forEach { p ->
                    Text(p, style = Serif)
                    Spacer(Modifier.height(10.dp))
                }
                x.validUntil?.let {
                    Text(buildAnnotatedString { append("This $noun is valid until "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(months(it)) }; append(".") },
                        style = Serif)
                }
                Spacer(Modifier.height(30.dp))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Box(Modifier.width(170.dp).height(1.dp).background(Ink))
                        Spacer(Modifier.height(4.dp))
                        Text(x.decidedByName, style = Serif.copy(fontSize = 13.sp))
                        if (x.decidedByRole.isNotBlank()) Text(x.decidedByRole, style = Serif.copy(fontSize = 11.sp, lineHeight = 15.sp, color = Grey))
                        Text("For: Chief Executive Officer", style = Serif.copy(fontSize = 11.sp, color = Grey))
                    }
                    Box(Modifier.size(110.dp, 72.dp).border(1.dp, Color(0xFF999999)), contentAlignment = Alignment.Center) {
                        Text("Council date stamp", style = Serif.copy(fontSize = 10.sp, color = Color(0xFF888888)))
                    }
                }
                Spacer(Modifier.height(24.dp))
                Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFFBBBBBB)))
                Spacer(Modifier.height(4.dp))
                Text("Verify this $noun with the council quoting number $number · Chipinge Rural District Council – Client Charter 2026-2030",
                    Modifier.fillMaxWidth(), style = Serif.copy(fontSize = 9.sp, lineHeight = 12.sp, color = Grey, textAlign = TextAlign.Center))
            }
            error?.let { InfoBox(it, CrdcColors.Danger) }
            PrimaryButton("Print / save as PDF (A4)", busy = busy, onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        val link = ctx.sdk.postJson("certificates/${x.id}/print-link/", buildJsonObject { })
                        (link["url"] as? JsonPrimitive)?.content?.let { uri.openUri(it) }
                    }.onFailure { error = it.message ?: "No connection. Try again when you are online." }
                    busy = false
                }
            })
        }
    }
}
