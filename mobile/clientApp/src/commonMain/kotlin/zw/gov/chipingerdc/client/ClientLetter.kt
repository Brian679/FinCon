package zw.gov.chipingerdc.client

import androidx.compose.foundation.Canvas
import org.jetbrains.compose.resources.Font
import zw.gov.chipingerdc.client.resources.Res
import zw.gov.chipingerdc.client.resources.liberation_serif_bold
import zw.gov.chipingerdc.client.resources.liberation_serif_regular
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
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

/**
 * The issued letter, drawn exactly like the printed A4 copy: the page is laid out in CSS pixels of an A4 sheet
 * (794 × 1123 px – the same margins, font sizes and line spacing as the print template) and scaled to the screen width.
 */
@Composable
fun CertificateViewScreen(ctx: CCtx, id: String) {
    val c by ctx.sdk.observeOne(Entities.CERTIFICATES, id, Certificate.serializer()).collectAsState(initial = null)
    val scope = rememberCoroutineScope()
    val uri = androidx.compose.ui.platform.LocalUriHandler.current
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AppScreen("Letter", onBack = ctx::back) {
        val x = c ?: return@AppScreen Empty("Not found")
        Column(Modifier.fillMaxWidth().background(Color(0xFFE9E9E9)).verticalScroll(rememberScrollState()).padding(vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.padding(horizontal = 12.dp)) { PrimaryButton("Print / save as PDF (A4)", busy = busy, onClick = {
                busy = true
                scope.launch {
                    runCatching {
                        val link = ctx.sdk.postJson("certificates/${x.id}/print-link/", buildJsonObject { })
                        (link["url"] as? JsonPrimitive)?.content?.let { uri.openUri(it) }
                    }.onFailure { error = it.message ?: "No connection. Try again when you are online." }
                    busy = false
                }
            }) }
            error?.let { Box(Modifier.padding(12.dp)) { InfoBox(it, CrdcColors.Danger) } }
            Spacer(Modifier.height(10.dp))
            A4Letter(x, Modifier.padding(horizontal = 8.dp))
        }
    }
}

@Composable
fun A4Letter(x: Certificate, modifier: Modifier = Modifier) {
    val (title, noun) = when (x.kind) {
        "RESIDENCE" -> "CONFIRMATION OF RESIDENCE" to "letter"; "CLEARANCE" -> "RATES CLEARANCE CERTIFICATE" to "certificate"
        "OWNERSHIP" -> "CONFIRMATION OF STAND OWNERSHIP" to "letter"; "CESSION" -> "APPROVAL OF CESSION (TRANSFER) OF STAND" to "letter"
        "BURIAL" -> "BURIAL ORDER" to "order"; else -> x.kindLabel.uppercase() to "letter"
    }
    val number = x.number.ifBlank { x.reference }
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val k = maxWidth.value / 794f                     // screen dp per A4 CSS pixel
        fun px(v: Float) = (v * k).dp
        val outer = LocalDensity.current
        CompositionLocalProvider(LocalDensity provides Density(outer.density, 1f)) {   // the page keeps its size whatever the phone's text size
            fun fs(v: Float) = (v * k).sp
            val times = FontFamily(Font(Res.font.liberation_serif_regular, FontWeight.Normal), Font(Res.font.liberation_serif_bold, FontWeight.Bold))
            val base = TextStyle(fontFamily = times, color = Ink, fontSize = fs(16f), lineHeight = fs(24f))
            Column(Modifier.fillMaxWidth().height(px(1123f)).shadow(px(6f)).background(Color.White)
                .padding(start = px(68f), end = px(68f), top = px(68f), bottom = px(45f))) {
                // letterhead
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CouncilCrest(Modifier.size(px(72f)))
                    Spacer(Modifier.width(px(14f)))
                    Column {
                        Text("CHIPINGE RURAL DISTRICT COUNCIL", style = base.copy(fontSize = fs(22.7f), lineHeight = fs(30f), fontWeight = FontWeight.Bold,
                            color = CrdcColors.Green, letterSpacing = fs(0.5f)))
                        Text("858 E.D. Mnangagwa Street, P.O. Box 19, Chipinge, Zimbabwe\nTel: +263 227 204 5631-5 · Email: info@chipingerdc.gov.zw\n" +
                            "Facebook: chipingerdc · X: @chipingerdc\nAll correspondence to be addressed to the Chief Executive Officer",
                            style = base.copy(fontSize = fs(12.7f), lineHeight = fs(17f), color = Color(0xFF333333)))
                    }
                }
                Spacer(Modifier.height(px(8f)))
                Box(Modifier.fillMaxWidth().height(px(1f).coerceAtLeast(0.7.dp)).background(CrdcColors.Green))
                Spacer(Modifier.height(px(1.5f).coerceAtLeast(1.dp)))
                Box(Modifier.fillMaxWidth().height(px(1f).coerceAtLeast(0.7.dp)).background(CrdcColors.Green))
                Spacer(Modifier.height(px(14f)))
                Row(Modifier.fillMaxWidth()) {
                    val ref = base.copy(fontSize = fs(14.7f), lineHeight = fs(22f))
                    Column(Modifier.weight(1f)) {
                        Text(buildAnnotatedString { append("Our ref: "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(number) } }, style = ref)
                        Text("Your ref: ${x.reference}", style = ref)
                    }
                    Text(months(x.decidedAt ?: x.createdAt), style = ref)
                }
                Spacer(Modifier.height(px(10f)))
                Text("TO WHOM IT MAY CONCERN", style = base)
                Spacer(Modifier.height(px(11f + 18f)))
                Text(title, Modifier.fillMaxWidth(), style = base.copy(fontSize = fs(18f), lineHeight = fs(27f), fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center, textDecoration = TextDecoration.Underline, letterSpacing = fs(0.5f)))
                Spacer(Modifier.height(px(14f)))
                letterBody(x).forEach { para ->
                    Text(para, Modifier.fillMaxWidth(), style = base.copy(textAlign = TextAlign.Justify))
                    Spacer(Modifier.height(px(11f)))
                }
                x.validUntil?.let {
                    Text(buildAnnotatedString { append("This $noun is valid until "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(months(it)) }; append(".") },
                        style = base)
                    Spacer(Modifier.height(px(11f)))
                }
                Spacer(Modifier.height(px(31f)))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.width(px(265f))) {
                        Box(Modifier.fillMaxWidth().height(px(1f).coerceAtLeast(0.5.dp)).background(Ink))
                        Spacer(Modifier.height(px(4f)))
                        val small = base.copy(fontSize = fs(12.2f), lineHeight = fs(22f))
                        Text(x.decidedByName, style = base.copy(fontSize = fs(14.7f), lineHeight = fs(22f)))
                        if (x.decidedByRole.isNotBlank()) Text(x.decidedByRole, style = small)
                        Text("For: Chief Executive Officer", style = small)
                    }
                    Spacer(Modifier.weight(1f))
                    Box(Modifier.size(px(159f), px(113f)).drawBehind {
                        drawRect(Color(0xFF888888), style = Stroke(width = 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 3f))))
                    }, contentAlignment = Alignment.Center) {
                        Text("Council date stamp", style = base.copy(fontSize = fs(12f), color = Color(0xFF888888)))
                    }
                }
                Spacer(Modifier.weight(1f))
                Box(Modifier.fillMaxWidth().height(px(1f).coerceAtLeast(0.5.dp)).background(Color(0xFFBBBBBB)))
                Spacer(Modifier.height(px(5f)))
                Text("Verify this $noun with the council quoting number $number · Chipinge Rural District Council – Client Charter 2026-2030",
                    Modifier.fillMaxWidth(), style = base.copy(fontSize = fs(11.3f), lineHeight = fs(17f), color = Grey, textAlign = TextAlign.Center))
            }
        }
    }
}
