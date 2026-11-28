package zw.gov.chipingerdc.shared

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import zw.gov.chipingerdc.db.CouncilDatabase
import java.io.File
import java.util.Properties

/**
 * Desktop: the offline database is a file in the user's home folder
 * (Windows: C:\Users\<name>\.chipinge-rdc, macOS / Linux: ~/.chipinge-rdc),
 * so work saved while offline survives closing the app and restarting the computer.
 * [folder] can be overridden (e.g. one folder per Windows user on a shared PC).
 */
actual class DatabaseDriverFactory(private val folder: File = File(System.getProperty("user.home"), ".chipinge-rdc")) {
    actual fun createDriver(name: String): SqlDriver {
        folder.mkdirs()
        val file = File(folder, name)
        return JdbcSqliteDriver("jdbc:sqlite:${file.absolutePath}", Properties(), CouncilDatabase.Schema)
    }
}

/** Desktop has no hardware back button: the Esc key goes back (wired in each app's main window). */
object DesktopKeys {
    @Volatile var back: (() -> Unit)? = null
}

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) {
    val current by rememberUpdatedState(onBack)
    DisposableEffect(enabled) {
        DesktopKeys.back = if (enabled) ({ current() }) else null
        onDispose { DesktopKeys.back = null }
    }
}

actual val platformName: String = "Desktop (${System.getProperty("os.name")})"


@Composable
actual fun rememberFilePicker(onPicked: (PickedFile?) -> Unit): () -> Unit {
    val callback by rememberUpdatedState(onPicked)
    return {
        val dialog = java.awt.FileDialog(null as java.awt.Frame?, "Choose the file", java.awt.FileDialog.LOAD)
        dialog.isVisible = true
        val file = dialog.file?.let { File(dialog.directory, it) }
        callback(file?.let { PickedFile(it.name, it.readBytes(), java.nio.file.Files.probeContentType(it.toPath()) ?: "application/octet-stream") })
    }
}


/** Desktop computers use a scanner: the scanned file is chosen from disk. */
@Composable
actual fun rememberCameraCapture(onPicked: (PickedFile?) -> Unit): () -> Unit = rememberFilePicker(onPicked)
