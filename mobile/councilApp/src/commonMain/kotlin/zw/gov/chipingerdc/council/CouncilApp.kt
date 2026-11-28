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
import zw.gov.chipingerdc.shared.ui.LocalMenuOpener
import zw.gov.chipingerdc.shared.ui.AppScreen
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import zw.gov.chipingerdc.shared.ui.LocalSiteName
import zw.gov.chipingerdc.shared.ui.CrdcColors
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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
    data object Certificates : Screen
    data class CertificateDetail(val id: String) : Screen
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
    // finance & administration registers (same as the staff website)
    data object Vouchers : Screen
    data class NewVoucher(val poId: String?) : Screen
    data object CashUps : Screen
    data object Orders : Screen
    data class OrderDetail(val id: String) : Screen
    data object Correspondence : Screen
    data class CorrespondenceDetail(val id: String) : Screen
    data object NewCorrespondence : Screen
    data object Staff : Screen
    data object FinanceReport : Screen
    data object Executive : Screen
    data object AuditTrail : Screen
    // profile & payroll
    data object MyProfile : Screen
    data object Payroll : Screen
    data class PayslipDetail(val id: String) : Screen
    data object Salaries : Screen
    data class SalaryEdit(val employeeId: Long) : Screen
    data object Arrears : Screen
    data object TaxTables : Screen
    data object NewLicence : Screen
    data class Register(val key: String) : Screen
    data class RegisterItem(val key: String, val id: String) : Screen
    data class RegisterForm(val key: String, val id: String?) : Screen
    data object NewHunt : Screen
    data class LeaveDetail(val id: String) : Screen
    data object DataHub : Screen
    data object NewFine : Screen
}

/** Everything a screen needs. */
class Ctx(val sdk: CouncilSdk, val nav: Navigator<Screen>, val me: Me, val sync: SyncState, val pending: Long, val fromMenu: Boolean = false,
          val afterGo: (() -> Unit)? = null) {
    /** From the menu a new register replaces what is open; elsewhere it opens on top (Back returns). */
    fun go(s: Screen) {
        if (fromMenu) { nav.replaceAll(Screen.Home); if (s != Screen.Home) nav.push(s) } else nav.push(s)
        afterGo?.invoke()
    }
    fun back() = nav.pop()
    fun syncNow() { sdk.syncNow() }
}

@Composable
fun CouncilApp(sdk: CouncilSdk) {
    CouncilTheme {
        val me by sdk.user.collectAsState()
        val user = me
        if (user == null) {
            LoginScreen(sdk, "Council staff app",
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
fun CouncilRouter(ctx: Ctx, profileOpen: Boolean = false, menuOpen: Boolean = false) {
    val unread by ctx.sdk.observe(zw.gov.chipingerdc.shared.model.Entities.NOTIFICATIONS, zw.gov.chipingerdc.shared.model.AppNotification.serializer())
        .collectAsState(initial = emptyList())
    val n = unread.count { !it.isRead }
    val me = ctx.me
    val profile = Profile(
        name = me.fullName.ifBlank { me.username }, lines = listOf(me.roleLabel, me.departmentLabel, me.email).filter { it.isNotBlank() },
        badge = n, startOpen = profileOpen,
        items = listOf(
            ProfileItem("My profile, leave & payslips") { ctx.go(Screen.MyProfile) },
            ProfileItem("Apply for leave") { ctx.go(Screen.NewLeave) },
            ProfileItem("Notifications", n) { ctx.go(Screen.Notifications) },
            ProfileItem("Change password") { ctx.go(Screen.ChangePassword) },
            ProfileItem("Sync centre", ctx.pending.toInt()) { ctx.go(Screen.SyncCentre) },
            ProfileItem("Log out", danger = true) { ctx.sdk.logout() },
        ),
    )
    CompositionLocalProvider(LocalProfile provides profile) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            if (maxWidth >= 900.dp) {
                // Desktop / tablet: menu on the left, the open register on the right.
                Row(Modifier.fillMaxSize()) {
                    Box(Modifier.width(360.dp).fillMaxHeight()) {
                        CompositionLocalProvider(LocalProfile provides null) {
                            AppScreen("Menu – ${ctx.me.departmentLabel}") { CouncilMenu(Ctx(ctx.sdk, ctx.nav, ctx.me, ctx.sync, ctx.pending, fromMenu = true)) }
                        }
                    }
                    Box(Modifier.width(1.dp).fillMaxHeight().background(CrdcColors.Border))
                    Box(Modifier.weight(1f).fillMaxHeight()) {
                        CompositionLocalProvider(LocalSiteName provides "") { CouncilScreens(ctx) }
                    }
                }
            } else {
                // Phone: the dashboard first; the menu slides in from the menu icon (top left).
                val drawer = rememberDrawerState(if (menuOpen) DrawerValue.Open else DrawerValue.Closed)
                val scope = rememberCoroutineScope()
                ModalNavigationDrawer(drawerState = drawer, drawerContent = {
                    ModalDrawerSheet(Modifier.width(320.dp), drawerContainerColor = androidx.compose.ui.graphics.Color.White,
                        // the panel draws its own header under the status bar – do not add the inset twice
                        windowInsets = androidx.compose.foundation.layout.WindowInsets(0, 0, 0, 0)) {
                        CompositionLocalProvider(LocalProfile provides null) {
                            AppScreen("Menu – ${ctx.me.departmentLabel}") {
                                CouncilMenu(Ctx(ctx.sdk, ctx.nav, ctx.me, ctx.sync, ctx.pending, fromMenu = true, afterGo = { scope.launch { drawer.close() } }))
                            }
                        }
                    }
                }) {
                    CompositionLocalProvider(LocalMenuOpener provides { scope.launch { drawer.open() } }) { CouncilScreens(ctx) }
                }
            }
        }
    }
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
        Screen.Certificates -> CertificatesToIssueScreen(ctx)
        is Screen.CertificateDetail -> CertificateDetailScreen(ctx, s.id)
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
        Screen.Vouchers -> VouchersScreen(ctx)
        is Screen.NewVoucher -> NewVoucherScreen(ctx, s.poId)
        Screen.CashUps -> CashUpsScreen(ctx)
        Screen.Orders -> OrdersScreen(ctx)
        is Screen.OrderDetail -> OrderDetailScreen(ctx, s.id)
        Screen.Correspondence -> CorrespondenceScreen(ctx)
        is Screen.CorrespondenceDetail -> CorrespondenceDetailScreen(ctx, s.id)
        Screen.NewCorrespondence -> NewCorrespondenceScreen(ctx)
        Screen.Staff -> StaffScreen(ctx)
        Screen.FinanceReport -> FinanceReportScreen(ctx)
        Screen.Executive -> ExecutiveScreen(ctx)
        Screen.AuditTrail -> AuditTrailScreen(ctx)
        Screen.MyProfile -> MyProfileScreen(ctx)
        Screen.Payroll -> PayrollScreen(ctx)
        is Screen.PayslipDetail -> PayslipDetailScreen(ctx, s.id)
        Screen.Salaries -> SalariesScreen(ctx)
        is Screen.SalaryEdit -> SalaryEditScreen(ctx, s.employeeId)
        Screen.Arrears -> ArrearsScreen(ctx)
        Screen.TaxTables -> TaxTablesScreen(ctx)
        Screen.NewLicence -> NewLicenceScreen(ctx)
        is Screen.Register -> RegisterListScreen(ctx, s.key)
        is Screen.RegisterItem -> RegisterItemScreen(ctx, s.key, s.id)
        is Screen.RegisterForm -> RegisterFormScreen(ctx, s.key, s.id)
        Screen.NewHunt -> NewHuntScreen(ctx)
        is Screen.LeaveDetail -> LeaveDetailScreen(ctx, s.id)
        Screen.DataHub -> DataHubScreen(ctx)
        Screen.NewFine -> NewFineScreen(ctx)
    }
}
