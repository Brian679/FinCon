package zw.gov.chipingerdc.council

import androidx.compose.ui.window.ComposeUIViewController
import platform.UIKit.UIViewController
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.DatabaseDriverFactory
import zw.gov.chipingerdc.shared.model.AppKind

private var sdkInstance: CouncilSdk? = null

private fun sdk(serverUrl: String): CouncilSdk =
    sdkInstance ?: CouncilSdk(DatabaseDriverFactory(), AppKind.COUNCIL, serverUrl).also { sdkInstance = it }

/** Called from Swift: `MainViewControllerKt.MainViewController(serverUrl: ...)`. */
fun MainViewController(serverUrl: String): UIViewController = ComposeUIViewController { CouncilApp(sdk(serverUrl)) }

/** Called from the iOS app delegate on background fetch / when returning to the foreground. */
fun syncInBackground(serverUrl: String) {
    sdk(serverUrl).syncNow()
}
