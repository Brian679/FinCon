package zw.gov.chipingerdc.client

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import zw.gov.chipingerdc.shared.CouncilSdk
import zw.gov.chipingerdc.shared.ui.AppScreen
import zw.gov.chipingerdc.shared.PlatformBackHandler
import zw.gov.chipingerdc.shared.model.Me
import zw.gov.chipingerdc.shared.sync.SyncState
import androidx.compose.runtime.CompositionLocalProvider
import zw.gov.chipingerdc.shared.ui.ChangePasswordScreen
import zw.gov.chipingerdc.shared.ui.CouncilTheme
import zw.gov.chipingerdc.shared.ui.LocalProfile
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
    data object MyStands : CScreen
    data object RegisterStand : CScreen
    data object Plans : CScreen
    data object NewPlan : CScreen
    data object ChangePassword : CScreen
    data object Fines : CScreen
    data object FindFine : CScreen
    data object Permits : CScreen
    data object ApplyPermit : CScreen
    data object Notices : CScreen
    data object Accounts : CScreen
    data class PayBills(val ids: List<String>) : CScreen
    data object Statements : CScreen
    data object Certificates : CScreen
    data object RequestCertificate : CScreen
    data class CertificateView(val id: String) : CScreen
    data class StandPeople(val propertyId: String, val title: String) : CScreen
    data class StandPerson(val propertyId: String, val id: String?) : CScreen
}

class CCtx(val sdk: CouncilSdk, val nav: Navigator<CScreen>, val me: Me, val sync: SyncState, val pending: Long, val fromMenu: Boolean = false,
           val afterGo: () -> Unit = {}) {
    fun go(s: CScreen) {
        when {
            fromMenu && s == CScreen.Home -> nav.replaceAll(CScreen.Home)
            fromMenu -> { nav.replaceAll(CScreen.Home); nav.push(s) }
            else -> nav.push(s)
        }
        afterGo()
    }
    fun back() = nav.pop()
    fun syncNow() { sdk.syncNow() }
}

@Composable
fun ClientApp(sdk: CouncilSdk) {
    CouncilTheme(siteName = "Chipinge RDC online services") {
        val me by sdk.user.collectAsState()
        val user = me
        var registering by remember { mutableStateOf(false) }
        if (user == null) {
            if (registering) RegisterScreen(sdk) { registering = false }
            else LoginScreen(sdk, "", "", onRegister = { registering = true })
            return@CouncilTheme
        }
        val nav = remember(user.username) { Navigator<CScreen>(CScreen.Home) }
        val sync by sdk.sync.state.collectAsState()
        val pending by sdk.pendingCount.collectAsState(initial = 0L)
        LaunchedEffect(user.username) { sdk.sync.startAuto(sdk.scope) }
        PlatformBackHandler(nav.canGoBack) { nav.pop() }
        val ctx = CCtx(sdk, nav, user, sync, pending)
        ClientRouter(ctx)
    }
}


/** Shows the screen on top of the back stack (also used to render screens for documentation). */
@Composable
fun ClientRouter(ctx: CCtx, profileOpen: Boolean = false, menuOpen: Boolean = false) {
    val unread by ctx.sdk.observe(zw.gov.chipingerdc.shared.model.Entities.NOTIFICATIONS, zw.gov.chipingerdc.shared.model.AppNotification.serializer())
        .collectAsState(initial = emptyList())
    val n = unread.count { !it.isRead }
    val me = ctx.me
    val profile = Profile(
        name = me.fullName.ifBlank { me.username }, lines = listOf(me.username, me.phone, me.email).filter { it.isNotBlank() },
        badge = n, startOpen = profileOpen,
        items = listOf(
            ProfileItem("Notifications", n) { ctx.go(CScreen.Notifications) },
            ProfileItem("Link a council account") { ctx.go(CScreen.LinkAccount) },
            ProfileItem("Statements") { ctx.go(CScreen.Statements) },
            ProfileItem("Client Charter") { ctx.go(CScreen.Charter) },
            ProfileItem("Change password") { ctx.go(CScreen.ChangePassword) },
            ProfileItem("Sync status", ctx.pending.toInt()) { ctx.go(CScreen.SyncCentre) },
            ProfileItem("Log out", danger = true) { ctx.sdk.logout() },
        ),
    )
    CompositionLocalProvider(LocalProfile provides profile) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            if (maxWidth >= 900.dp) {
                // Desktop / tablet: the menu on the left, the dashboard or the open service on the right.
                Row(Modifier.fillMaxSize()) {
                    Box(Modifier.width(360.dp).fillMaxHeight()) {
                        CompositionLocalProvider(LocalProfile provides null) {
                            AppScreen("Menu") { ClientMenu(CCtx(ctx.sdk, ctx.nav, ctx.me, ctx.sync, ctx.pending, fromMenu = true)) }
                        }
                    }
                    Box(Modifier.width(1.dp).fillMaxHeight().background(CrdcColors.Border))
                    Box(Modifier.weight(1f).fillMaxHeight()) {
                        CompositionLocalProvider(LocalSiteName provides "") { ClientScreens(ctx) }
                    }
                }
            } else {
                // Phone: the dashboard first; the menu slides in from the menu icon (top left).
                val drawer = androidx.compose.material3.rememberDrawerState(
                    if (menuOpen) androidx.compose.material3.DrawerValue.Open else androidx.compose.material3.DrawerValue.Closed)
                val scope = androidx.compose.runtime.rememberCoroutineScope()
                androidx.compose.material3.ModalNavigationDrawer(drawerState = drawer, drawerContent = {
                    androidx.compose.material3.ModalDrawerSheet(Modifier.width(320.dp), drawerContainerColor = androidx.compose.ui.graphics.Color.White,
                        windowInsets = androidx.compose.foundation.layout.WindowInsets(0, 0, 0, 0)) {
                        CompositionLocalProvider(LocalProfile provides null) {
                            AppScreen("Menu") {
                                ClientMenu(CCtx(ctx.sdk, ctx.nav, ctx.me, ctx.sync, ctx.pending, fromMenu = true,
                                    afterGo = { scope.launch { drawer.close() } }))
                            }
                        }
                    }
                }) {
                    CompositionLocalProvider(zw.gov.chipingerdc.shared.ui.LocalMenuOpener provides { scope.launch { drawer.open() } }) { ClientScreens(ctx) }
                }
            }
        }
    }
}

@Composable
private fun ClientScreens(ctx: CCtx) {
    when (val s = ctx.nav.current) {
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
        CScreen.MyStands -> MyStandsScreen(ctx)
        CScreen.RegisterStand -> RegisterStandScreen(ctx)
        CScreen.Plans -> PlansScreen(ctx)
        CScreen.NewPlan -> NewPlanScreen(ctx)
        CScreen.ChangePassword -> ChangePasswordScreen(ctx.sdk, ctx::back)
        CScreen.Fines -> FinesScreen(ctx)
        CScreen.FindFine -> FindFineScreen(ctx)
        CScreen.Permits -> PermitsScreen(ctx)
        CScreen.ApplyPermit -> ApplyPermitScreen(ctx)
        CScreen.Notices -> NoticesScreen(ctx)
        CScreen.Accounts -> AccountsScreen(ctx)
        is CScreen.PayBills -> PayBillsScreen(ctx, s.ids)
        CScreen.Statements -> StatementsScreen(ctx)
        CScreen.Certificates -> CertificatesScreen(ctx)
        CScreen.RequestCertificate -> RequestCertificateScreen(ctx)
        is CScreen.CertificateView -> CertificateViewScreen(ctx, s.id)
        is CScreen.StandPeople -> StandPeopleScreen(ctx, s.propertyId, s.title)
        is CScreen.StandPerson -> StandPersonScreen(ctx, s.propertyId, s.id)
    }
}
