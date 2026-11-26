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
import androidx.compose.runtime.CompositionLocalProvider
import zw.gov.chipingerdc.shared.ui.ChangePasswordScreen
import zw.gov.chipingerdc.shared.ui.CouncilTheme
import zw.gov.chipingerdc.shared.ui.LocalProfile
import zw.gov.chipingerdc.shared.ui.Profile
import zw.gov.chipingerdc.shared.ui.ProfileItem
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
    // department oversight & charter registers
    data class Department(val dept: String? = null) : Screen
    data object NewTask : Screen
    data object Requisitions : Screen
    data object NewRequisition : Screen
    data object Areas : Screen
    data class AreaBoard(val id: String) : Screen
    data object Claims : Screen
    data class ClaimDetail(val id: String) : Screen
    data object Leases : Screen
    data class StandDetail(val id: String) : Screen
    data class ProjectDetail(val id: String) : Screen
    data class FindingDetail(val id: String) : Screen
    data object Incidents : Screen
    data class IncidentDetail(val id: String) : Screen
    data object NewIncident : Screen
    data object Activities : Screen
    data class ActivityDetail(val id: String) : Screen
    data object NewActivity : Screen
    data object Plans : Screen
    data class PlanDetail(val id: String) : Screen
    data object Assets : Screen
    data class AssetDetail(val id: String) : Screen
    data object Risks : Screen
    data object Meetings : Screen
    data class MeetingDetail(val id: String) : Screen
    data object Resolutions : Screen
    data class ResolutionDetail(val id: String) : Screen
    data object Tickets : Screen
    data class TicketDetail(val id: String) : Screen
    data object NewTicket : Screen
    data object Policies : Screen
    // requests for funds & memos between departments
    data object Funds : Screen
    data class FundsDetail(val id: String) : Screen
    data object NewFunds : Screen
    data object Memos : Screen
    data class MemoDetail(val id: String) : Screen
    data object NewMemo : Screen
    data object ChangePassword : Screen
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
        CouncilRouter(ctx)
    }
}


/** Shows the screen on top of the back stack (also used to render screens for documentation). */
@Composable
fun CouncilRouter(ctx: Ctx, profileOpen: Boolean = false) {
    val unread by ctx.sdk.observe(zw.gov.chipingerdc.shared.model.Entities.NOTIFICATIONS, zw.gov.chipingerdc.shared.model.AppNotification.serializer())
        .collectAsState(initial = emptyList())
    val n = unread.count { !it.isRead }
    val me = ctx.me
    val profile = Profile(
        name = me.fullName.ifBlank { me.username }, lines = listOf(me.roleLabel, me.departmentLabel, me.email).filter { it.isNotBlank() },
        badge = n, startOpen = profileOpen,
        items = listOf(
            ProfileItem("Notifications", n) { ctx.go(Screen.Notifications) },
            ProfileItem("Change password") { ctx.go(Screen.ChangePassword) },
            ProfileItem("Sync centre", ctx.pending.toInt()) { ctx.go(Screen.SyncCentre) },
            ProfileItem("Log out", danger = true) { ctx.sdk.logout() },
        ),
    )
    CompositionLocalProvider(LocalProfile provides profile) { CouncilScreens(ctx) }
}

@Composable
private fun CouncilScreens(ctx: Ctx) {
    when (val s = ctx.nav.current) {
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
        is Screen.Department -> DepartmentScreen(ctx, s.dept)
        Screen.NewTask -> NewTaskScreen(ctx)
        Screen.Requisitions -> RequisitionsScreen(ctx)
        Screen.NewRequisition -> NewRequisitionScreen(ctx)
        Screen.Areas -> AreasScreen(ctx)
        is Screen.AreaBoard -> AreaBoardScreen(ctx, s.id)
        Screen.Claims -> ClaimsScreen(ctx)
        is Screen.ClaimDetail -> ClaimDetailScreen(ctx, s.id)
        Screen.Leases -> LeasesScreen(ctx)
        is Screen.StandDetail -> StandDetailScreen(ctx, s.id)
        is Screen.ProjectDetail -> ProjectDetailScreen(ctx, s.id)
        is Screen.FindingDetail -> FindingDetailScreen(ctx, s.id)
        Screen.Incidents -> IncidentsScreen(ctx)
        is Screen.IncidentDetail -> IncidentDetailScreen(ctx, s.id)
        Screen.NewIncident -> NewIncidentScreen(ctx)
        Screen.Activities -> ActivitiesScreen(ctx)
        is Screen.ActivityDetail -> ActivityDetailScreen(ctx, s.id)
        Screen.NewActivity -> NewActivityScreen(ctx)
        Screen.Plans -> PlansScreen(ctx)
        is Screen.PlanDetail -> PlanDetailScreen(ctx, s.id)
        Screen.Assets -> AssetsScreen(ctx)
        is Screen.AssetDetail -> AssetDetailScreen(ctx, s.id)
        Screen.Risks -> RisksScreen(ctx)
        Screen.Meetings -> MeetingsScreen(ctx)
        is Screen.MeetingDetail -> MeetingDetailScreen(ctx, s.id)
        Screen.Resolutions -> ResolutionsScreen(ctx)
        is Screen.ResolutionDetail -> ResolutionDetailScreen(ctx, s.id)
        Screen.Tickets -> TicketsScreen(ctx)
        is Screen.TicketDetail -> TicketDetailScreen(ctx, s.id)
        Screen.NewTicket -> NewTicketScreen(ctx)
        Screen.Policies -> PoliciesScreen(ctx)
        Screen.Funds -> FundsScreen(ctx)
        is Screen.FundsDetail -> FundsDetailScreen(ctx, s.id)
        Screen.NewFunds -> NewFundsScreen(ctx)
        Screen.Memos -> MemosScreen(ctx)
        is Screen.MemoDetail -> MemoDetailScreen(ctx, s.id)
        Screen.NewMemo -> NewMemoScreen(ctx)
        Screen.ChangePassword -> ChangePasswordScreen(ctx.sdk, ctx::back)
    }
}
