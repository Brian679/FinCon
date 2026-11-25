package zw.gov.chipingerdc.shared.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

object CrdcColors {
    val Green = Color(0xFF1F7A3A)
    val GreenDark = Color(0xFF155C2B)
    val Blue = Color(0xFF2A6DB0)
    val Maroon = Color(0xFF7A3B2E)
    val Gold = Color(0xFFF2C230)
    val Danger = Color(0xFFC0392B)
    val Warning = Color(0xFFD39E00)
    val Success = Color(0xFF1E8E3E)
    val Muted = Color(0xFF6C7A72)
    val Background = Color(0xFFF4F6F5)
}

@Composable
fun CouncilTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = CrdcColors.Green,
            onPrimary = Color.White,
            primaryContainer = Color(0xFFD7EEDD),
            onPrimaryContainer = CrdcColors.GreenDark,
            secondary = CrdcColors.Blue,
            onSecondary = Color.White,
            tertiary = CrdcColors.Maroon,
            background = CrdcColors.Background,
            surface = Color.White,
            error = CrdcColors.Danger,
        ),
        content = content,
    )
}
