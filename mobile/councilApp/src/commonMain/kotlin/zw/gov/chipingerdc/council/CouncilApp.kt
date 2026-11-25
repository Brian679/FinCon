package zw.gov.chipingerdc.council

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.PlatformBackHandler
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.sync.SyncState
import zw.gov.chipingerdc.shared.ui.CouncilTheme
import zw.gov.chipingerdc.shared.ui.LoginScreen
import zw.gov.chipingerdc.shared.ui.Navigator

/** Screens of the council staff app. */
sealed interface Screen {
    data object Home : Screen
    data object NewReceipt : Screen
    data class NewReceiptFor(val accountId: String?, val billId: String?) : Screen
    data object Receipts : Screen
    data class ReceiptDetail(val id: String) : Screen
    data object Accounts : Screen
    data class AccountDetail(val id: String) : Screen
    data object Licences : Screen
    data class LicenceDetail(val id: String) : Screen
    data object Approvals : Screen
    data class RequisitionDetail(val id: String) : Screen
    data class VoucherDetail(val id: String) : Screen
    data object Budget : Screen
    data object Tasks : Screen
    data class TaskDetail(val id: String) : Screen
    data object Complaints : Screen
    data class ComplaintDetail(val id: String) : Screen
    data object NewComplaint : Screen
    data object Requests : Screen
    data class RequestDetail(val id: String) : Screen
    data object NewRequest : Screen
    data object Projects : Screen
    data object Stands : Screen
    data object NewStand : Screen
    data object Findings : Screen
    data object Leave : Screen
    data object NewLeave : Screen
    data object Notifications : Screen
    data object SyncCentre : Screen
    data object Charter : Screen
}

/** Everything a screen needs. */
class Ctx(val sdk: CouncilSdk, val nav: Navigator<Screen>, val me: Me, val sync: SyncState, val pending: Long) {
    fun go(s: Screen) = nav.push(s)
    fun back() = nav.pop()
    fun syncNow() { sdk.syncNow() }
}

@Composable
fun CouncilApp(sdk: CouncilSdk) {
    CouncilTheme {
        val me by sdk.user.collectAsState()
        val user = me
        if (user == null) {
            LoginScreen(sdk, "Council staff app – Client Charter 2026-2030",
                "Staff accounts are issued by the ICT administrator. Work done offline syncs automatically.")
            return@CouncilTheme
        }
        val nav = remember(user.username) { Navigator<Screen>(Screen.Home) }
        val sync by sdk.sync.state.collectAsState()
        val pending by sdk.pendingCount.collectAsState(initial = 0L)
        LaunchedEffect(user.username) { sdk.sync.startAuto(sdk.scope) }
        PlatformBackHandler(nav.canGoBack) { nav.pop() }
        val ctx = Ctx(sdk, nav, user, sync, pending)
        when (val s = nav.current) {
            Screen.Home -> HomeScreen(ctx)
            Screen.NewReceipt -> ReceiptFormScreen(ctx, null, null)
            is Screen.NewReceiptFor -> ReceiptFormScreen(ctx, s.accountId, s.billId)
            Screen.Receipts -> ReceiptsScreen(ctx)
            is Screen.ReceiptDetail -> ReceiptDetailScreen(ctx, s.id)
            Screen.Accounts -> AccountsScreen(ctx)
            is Screen.AccountDetail -> AccountDetailScreen(ctx, s.id)
            Screen.Licences -> LicencesScreen(ctx)
            is Screen.LicenceDetail -> LicenceDetailScreen(ctx, s.id)
            Screen.Approvals -> ApprovalsScreen(ctx)
            is Screen.RequisitionDetail -> RequisitionDetailScreen(ctx, s.id)
            is Screen.VoucherDetail -> VoucherDetailScreen(ctx, s.id)
            Screen.Budget -> BudgetScreen(ctx)
            Screen.Tasks -> TasksScreen(ctx)
            is Screen.TaskDetail -> TaskDetailScreen(ctx, s.id)
            Screen.Complaints -> ComplaintsScreen(ctx)
            is Screen.ComplaintDetail -> ComplaintDetailScreen(ctx, s.id)
            Screen.NewComplaint -> ComplaintFormScreen(ctx)
            Screen.Requests -> RequestsScreen(ctx)
            is Screen.RequestDetail -> RequestDetailScreen(ctx, s.id)
            Screen.NewRequest -> RequestFormScreen(ctx)
            Screen.Projects -> ProjectsScreen(ctx)
            Screen.Stands -> StandsScreen(ctx)
            Screen.NewStand -> StandFormScreen(ctx)
            Screen.Findings -> FindingsScreen(ctx)
            Screen.Leave -> LeaveScreen(ctx)
            Screen.NewLeave -> LeaveFormScreen(ctx)
            Screen.Notifications -> NotificationsScreen(ctx)
            Screen.SyncCentre -> SyncCentreScreen(ctx)
            Screen.Charter -> CharterScreen(ctx)
        }
    }
}
