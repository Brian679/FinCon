package zw.gov.chipingerdc.client

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.PlatformBackHandler
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.sync.SyncState
import zw.gov.chipingerdc.shared.ui.CouncilTheme
import zw.gov.chipingerdc.shared.ui.LoginScreen
import zw.gov.chipingerdc.shared.ui.Navigator

sealed interface CScreen {
    data object Home : CScreen
    data object LinkAccount : CScreen
    data class Account(val id: String) : CScreen
    data class Pay(val accountId: String?, val billId: String?) : CScreen
    data class Payment(val reference: String) : CScreen
    data object Receipts : CScreen
    data class Receipt(val id: String) : CScreen
    data object Licences : CScreen
    data object ApplyLicence : CScreen
    data object Problems : CScreen
    data object ReportProblem : CScreen
    data object Feedback : CScreen
    data object NewFeedback : CScreen
    data object Stands : CScreen
    data object ApplyStand : CScreen
    data object Notifications : CScreen
    data object Charter : CScreen
    data object SyncCentre : CScreen
}

class CCtx(val sdk: CouncilSdk, val nav: Navigator<CScreen>, val me: Me, val sync: SyncState, val pending: Long) {
    fun go(s: CScreen) = nav.push(s)
    fun back() = nav.pop()
    fun syncNow() { sdk.syncNow() }
}

@Composable
fun ClientApp(sdk: CouncilSdk) {
    CouncilTheme {
        val me by sdk.user.collectAsState()
        val user = me
        var registering by remember { mutableStateOf(false) }
        if (user == null) {
            if (registering) RegisterScreen(sdk) { registering = false }
            else LoginScreen(sdk, "Pay rates & levies · licences · report problems",
                "Your information is kept private and confidential (Client Charter).", onRegister = { registering = true })
            return@CouncilTheme
        }
        val nav = remember(user.username) { Navigator<CScreen>(CScreen.Home) }
        val sync by sdk.sync.state.collectAsState()
        val pending by sdk.pendingCount.collectAsState(initial = 0L)
        LaunchedEffect(user.username) { sdk.sync.startAuto(sdk.scope) }
        PlatformBackHandler(nav.canGoBack) { nav.pop() }
        val ctx = CCtx(sdk, nav, user, sync, pending)
        when (val s = nav.current) {
            CScreen.Home -> ClientHome(ctx)
            CScreen.LinkAccount -> LinkAccountScreen(ctx)
            is CScreen.Account -> AccountScreen(ctx, s.id)
            is CScreen.Pay -> PayScreen(ctx, s.accountId, s.billId)
            is CScreen.Payment -> PaymentScreen(ctx, s.reference)
            CScreen.Receipts -> ReceiptsScreen(ctx)
            is CScreen.Receipt -> ReceiptScreen(ctx, s.id)
            CScreen.Licences -> LicencesScreen(ctx)
            CScreen.ApplyLicence -> ApplyLicenceScreen(ctx)
            CScreen.Problems -> ProblemsScreen(ctx)
            CScreen.ReportProblem -> ReportProblemScreen(ctx)
            CScreen.Feedback -> FeedbackScreen(ctx)
            CScreen.NewFeedback -> NewFeedbackScreen(ctx)
            CScreen.Stands -> StandsScreen(ctx)
            CScreen.ApplyStand -> ApplyStandScreen(ctx)
            CScreen.Notifications -> NotificationsScreen(ctx)
            CScreen.Charter -> CharterScreen(ctx)
            CScreen.SyncCentre -> SyncCentreScreen(ctx)
        }
    }
}
