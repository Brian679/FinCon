package zw.gov.chipingerdc.shared

import androidx.compose.runtime.Composable
import app.cash.sqldelight.db.SqlDriver

/** Creates the platform SQLite driver (Android: AndroidSqliteDriver, iOS: NativeSqliteDriver). */
expect class DatabaseDriverFactory {
    fun createDriver(name: String): SqlDriver
}

/** Hardware / gesture back navigation (Android back button; no-op on iOS). */
@Composable
expect fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit)

expect val platformName: String

/** A file the user picked (e.g. a building plan PDF or photo). */
class PickedFile(val name: String, val bytes: ByteArray, val mime: String)

/** Returns a function that opens the platform's file chooser; [onPicked] gets the file, or null when cancelled. */
@Composable
expect fun rememberFilePicker(onPicked: (PickedFile?) -> Unit): () -> Unit
