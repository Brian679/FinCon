package zw.gov.chipingerdc.shared

import androidx.compose.runtime.Composable
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.native.NativeSqliteDriver
import platform.UIKit.UIDevice
import zw.gov.chipingerdc.db.CouncilDatabase

actual class DatabaseDriverFactory {
    actual fun createDriver(name: String): SqlDriver = NativeSqliteDriver(CouncilDatabase.Schema, name)
}

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) {
    // iOS uses the on-screen "Back" button in the top bar.
}

actual val platformName: String = UIDevice.currentDevice.systemName() + " " + UIDevice.currentDevice.systemVersion
