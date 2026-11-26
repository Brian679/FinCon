package zw.gov.chipingerdc.client

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

/** Ratepayer / shop-owner desktop application (same features as the phone app). */
fun main() = application {
    val server = System.getProperty("crdc.server") ?: System.getenv("CRDC_SERVER_URL") ?: "https://www.chipingerdc.gov.zw"
    val sdk = CouncilSdk(DatabaseDriverFactory(), AppKind.CLIENT, server)
    Window(onCloseRequest = ::exitApplication, title = "Chipinge RDC – Online services", state = rememberWindowState(size = DpSize(1180.dp, 800.dp)),
        onKeyEvent = { e -> if (e.type == KeyEventType.KeyUp && e.key == Key.Escape) { DesktopKeys.back?.invoke(); true } else false }) {
        ClientApp(sdk)
    }
}
