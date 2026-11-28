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


@Composable
actual fun rememberCameraCapture(onPicked: (PickedFile?) -> Unit): () -> Unit {
    val context = androidx.compose.ui.platform.LocalContext.current
    val callback = androidx.compose.runtime.rememberUpdatedState(onPicked)
    val fallback = rememberFilePicker(onPicked)
    val target = androidx.compose.runtime.remember { arrayOfNulls<java.io.File>(1) }
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.TakePicture()) { ok ->
        val f = target[0]
        if (ok && f != null && f.length() > 0) {
            val stamp = java.text.SimpleDateFormat("yyyyMMdd-HHmm", java.util.Locale.US).format(java.util.Date())
            callback.value(PickedFile("scan-$stamp.jpg", f.readBytes(), "image/jpeg"))
        } else callback.value(null)
        f?.delete()
    }
    return {
        val dir = java.io.File(context.cacheDir, "scans").apply { mkdirs() }
        val f = java.io.File.createTempFile("scan", ".jpg", dir)
        target[0] = f
        val uri = androidx.core.content.FileProvider.getUriForFile(context, context.packageName + ".crdcfiles", f)
        try { launcher.launch(uri) } catch (e: android.content.ActivityNotFoundException) { fallback() }
    }
}
