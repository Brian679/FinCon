package zw.gov.chipingerdc.shared

import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import zw.gov.chipingerdc.db.CouncilDatabase

actual class DatabaseDriverFactory(private val context: Context) {
    actual fun createDriver(name: String): SqlDriver = AndroidSqliteDriver(CouncilDatabase.Schema, context, name)
}

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) = BackHandler(enabled, onBack)

actual val platformName: String = "Android ${android.os.Build.VERSION.RELEASE}"
