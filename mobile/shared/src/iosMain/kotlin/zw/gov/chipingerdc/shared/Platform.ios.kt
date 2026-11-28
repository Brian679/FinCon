package zw.gov.chipingerdc.shared

import androidx.compose.runtime.Composable
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.native.NativeSqliteDriver
import kotlinx.cinterop.addressOf
import kotlinx.cinterop.usePinned
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


private class PlanPickerDelegate(var onPicked: (PickedFile?) -> Unit) : platform.darwin.NSObject(), platform.UIKit.UIDocumentPickerDelegateProtocol {
    @OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
    override fun documentPicker(controller: platform.UIKit.UIDocumentPickerViewController, didPickDocumentsAtURLs: List<*>) {
        val url = didPickDocumentsAtURLs.firstOrNull() as? platform.Foundation.NSURL
        if (url == null) { onPicked(null); return }
        val scoped = url.startAccessingSecurityScopedResource()
        val data = platform.Foundation.NSData.dataWithContentsOfURL(url)
        if (scoped) url.stopAccessingSecurityScopedResource()
        val length = data?.length?.toInt() ?: 0
        if (data == null || length == 0) { onPicked(null); return }
        val bytes = ByteArray(length)
        bytes.usePinned { pinned -> platform.posix.memcpy(pinned.addressOf(0), data.bytes, data.length) }
        onPicked(PickedFile(url.lastPathComponent ?: "plan", bytes, "application/octet-stream"))
    }

    override fun documentPickerWasCancelled(controller: platform.UIKit.UIDocumentPickerViewController) = onPicked(null)
}

@Composable
actual fun rememberFilePicker(onPicked: (PickedFile?) -> Unit): () -> Unit {
    val delegate = androidx.compose.runtime.remember { PlanPickerDelegate(onPicked) }
    delegate.onPicked = onPicked
    return {
        val picker = platform.UIKit.UIDocumentPickerViewController(
            forOpeningContentTypes = listOf(platform.UniformTypeIdentifiers.UTTypePDF, platform.UniformTypeIdentifiers.UTTypeImage,
                platform.UniformTypeIdentifiers.UTTypeData), asCopy = true)
        picker.delegate = delegate
        platform.UIKit.UIApplication.sharedApplication.keyWindow?.rootViewController?.presentViewController(picker, animated = true, completion = null)
    }
}


private class CameraDelegate(var onPicked: (PickedFile?) -> Unit) : platform.darwin.NSObject(), platform.UIKit.UIImagePickerControllerDelegateProtocol,
    platform.UIKit.UINavigationControllerDelegateProtocol {
    @OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
    override fun imagePickerController(picker: platform.UIKit.UIImagePickerController, didFinishPickingMediaWithInfo: Map<Any?, *>) {
        picker.dismissViewControllerAnimated(true, completion = null)
        val image = didFinishPickingMediaWithInfo[platform.UIKit.UIImagePickerControllerOriginalImage] as? platform.UIKit.UIImage
        val data = image?.let { platform.UIKit.UIImageJPEGRepresentation(it, 0.8) }
        val length = data?.length?.toInt() ?: 0
        if (data == null || length == 0) { onPicked(null); return }
        val bytes = ByteArray(length)
        bytes.usePinned { pinned -> platform.posix.memcpy(pinned.addressOf(0), data.bytes, data.length) }
        onPicked(PickedFile("scan.jpg", bytes, "image/jpeg"))
    }

    override fun imagePickerControllerDidCancel(picker: platform.UIKit.UIImagePickerController) {
        picker.dismissViewControllerAnimated(true, completion = null)
        onPicked(null)
    }
}

@Composable
actual fun rememberCameraCapture(onPicked: (PickedFile?) -> Unit): () -> Unit {
    val delegate = androidx.compose.runtime.remember { CameraDelegate(onPicked) }
    delegate.onPicked = onPicked
    val fallback = rememberFilePicker(onPicked)
    return {
        val camera = platform.UIKit.UIImagePickerControllerSourceType.UIImagePickerControllerSourceTypeCamera
        if (!platform.UIKit.UIImagePickerController.isSourceTypeAvailable(camera)) fallback() else {
            val picker = platform.UIKit.UIImagePickerController()
            picker.sourceType = camera
            picker.delegate = delegate
            platform.UIKit.UIApplication.sharedApplication.keyWindow?.rootViewController?.presentViewController(picker, animated = true, completion = null)
        }
    }
}
