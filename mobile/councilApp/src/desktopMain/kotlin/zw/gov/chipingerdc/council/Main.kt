package zw.gov.chipingerdc.council

import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.DatabaseDriverFactory
import zw.gov.chipingerdc.shared.DesktopKeys
import zw.gov.chipingerdc.shared.model.AppKind

/**
 * Council staff desktop application (Windows, macOS, Linux) – the same screens,
 * offline database and sync as the Android / iOS council app. On a wide window the
 * menu stays on the left and the selected register opens on the right.
 *
 * Server address: set CRDC_SERVER_URL, start with -Dcrdc.server=..., or change it
 * under "Server settings" on the login screen.
 */
fun main() = application {
    val server = System.getProperty("crdc.server") ?: System.getenv("CRDC_SERVER_URL") ?: "https://staff.chipingerdc.gov.zw"
    val sdk = CouncilSdk(DatabaseDriverFactory(), AppKind.COUNCIL, server)
    Window(
        onCloseRequest = ::exitApplication,
        title = "Chipinge RDC – Council",
        state = rememberWindowState(size = DpSize(1280.dp, 820.dp)),
        onKeyEvent = { e -> if (e.type == KeyEventType.KeyUp && e.key == Key.Escape) { DesktopKeys.back?.invoke(); true } else false },
    ) {
        CouncilApp(sdk)
    }
}
