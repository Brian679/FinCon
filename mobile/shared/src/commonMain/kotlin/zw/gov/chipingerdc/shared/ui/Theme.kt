package zw.gov.chipingerdc.shared.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Council colours, applied with the Django-admin design language
 * (header + breadcrumbs bar, module caption bars, plain table rows, square buttons).
 */
object CrdcColors {
    // council palette
    val Green = Color(0xFF1F7A3A)        // header, captions, buttons
    val GreenDark = Color(0xFF155C2B)    // breadcrumbs bar, default (important) buttons
    val GreenLight = Color(0xFF5AA36C)
    val Blue = Color(0xFF2A6DB0)         // links
    val Gold = Color(0xFFF2C230)         // site name / header rule
    val Maroon = Color(0xFF7A3B2E)

    // Django admin neutrals
    val Body = Color(0xFF333333)
    val Muted = Color(0xFF666666)
    val Medium = Color(0xFF444444)
    val Hairline = Color(0xFFE8E8E8)
    val Border = Color(0xFFCCCCCC)
    val Darkened = Color(0xFFF8F8F8)
    val Selected = Color(0xFFFDF6D8)
    val CloseButton = Color(0xFF747474)
    val BreadcrumbsText = Color(0xFFCFE8D6)

    // statuses / messages
    val Danger = Color(0xFFBA2121)
    val Warning = Color(0xFF8A6D00)
    val Success = Color(0xFF1F7A3A)
    val MsgSuccess = Color(0xFFE2F2E6)
    val MsgWarning = Color(0xFFFDF3CC)
    val MsgError = Color(0xFFFFEFEF)
    val MsgInfo = Color(0xFFE3EEF8)
    val Background = Color.White
}

/** Site name shown in the header, e.g. "Chipinge RDC administration". */
val LocalSiteName = staticCompositionLocalOf { "Chipinge RDC" }

@Composable
fun CouncilTheme(siteName: String = "Chipinge RDC administration", content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalSiteName provides siteName) {
        MaterialTheme(
            colorScheme = lightColorScheme(
                primary = CrdcColors.Green,
                onPrimary = Color.White,
                primaryContainer = CrdcColors.MsgSuccess,
                onPrimaryContainer = CrdcColors.GreenDark,
                secondary = CrdcColors.Blue,
                onSecondary = Color.White,
                tertiary = CrdcColors.Maroon,
                background = Color.White,
                surface = Color.White,
                onSurface = CrdcColors.Body,
                outline = CrdcColors.Border,
                error = CrdcColors.Danger,
            ),
            content = content,
        )
    }
}
