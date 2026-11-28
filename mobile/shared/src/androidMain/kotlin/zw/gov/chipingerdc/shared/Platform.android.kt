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


@Composable
actual fun rememberFilePicker(onPicked: (PickedFile?) -> Unit): () -> Unit {
    val context = androidx.compose.ui.platform.LocalContext.current
    val callback = androidx.compose.runtime.rememberUpdatedState(onPicked)
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) {
            callback.value(null)
        } else {
            val cr = context.contentResolver
            val name = cr.query(uri, null, null, null, null)?.use { c ->
                val i = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                if (i >= 0 && c.moveToFirst()) c.getString(i) else null
            } ?: "plan"
            val bytes = cr.openInputStream(uri)?.use { it.readBytes() }
            callback.value(bytes?.let { PickedFile(name, it, cr.getType(uri) ?: "application/octet-stream") })
        }
    }
    return { launcher.launch(arrayOf("application/pdf", "image/*", "*/*")) }
}
