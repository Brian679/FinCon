package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.DpOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import zw.gov.chipingerdc.shared.CouncilSdk

/** One entry of the profile drop-down. */
data class ProfileItem(val label: String, val count: Int = 0, val danger: Boolean = false, val onClick: () -> Unit)

/** Who is logged in, shown behind the round profile icon at the top right of every screen. */
data class Profile(val name: String, val lines: List<String>, val items: List<ProfileItem>, val badge: Int = 0, val startOpen: Boolean = false)

val LocalProfile = staticCompositionLocalOf<Profile?> { null }

fun initials(name: String): String =
    name.split(" ", ".", "_").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }.ifBlank { "?" }

@Composable
fun Avatar(name: String, size: Int = 34, border: Color = Color.White) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(CrdcColors.Gold).border(2.dp, border, CircleShape), contentAlignment = Alignment.Center) {
        Text(initials(name), color = CrdcColors.GreenDark, fontWeight = FontWeight.Bold, fontSize = (size * 0.38).sp)
    }
}

/** The round icon with the drop-down: profile card, notifications, change password, log out. */
@Composable
fun ProfileButton(p: Profile) {
    var open by remember { mutableStateOf(p.startOpen) }
    Box {
        Row(Modifier.clickable { open = true }.padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(44.dp, 40.dp)) {
                Box(Modifier.align(Alignment.BottomStart)) { Avatar(p.name) }
                if (p.badge > 0) Text(p.badge.toString(), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.align(Alignment.TopEnd).clip(CircleShape).background(CrdcColors.Danger).padding(horizontal = 5.dp, vertical = 1.dp))
            }
            Text(" ▾", color = Color.White, fontSize = 12.sp)
        }
        DropdownMenu(open, { open = false }, offset = DpOffset(0.dp, 6.dp), modifier = Modifier.widthIn(min = 260.dp).background(Color.White)) {
            Row(Modifier.fillMaxWidth().background(CrdcColors.Darkened).bottomRule().padding(14.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Avatar(p.name, 46, CrdcColors.Hairline)
                Column {
                    Text(p.name, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = CrdcColors.Body)
                    p.lines.forEach { Text(it, fontSize = 12.sp, color = CrdcColors.Muted) }
                }
            }
            p.items.forEach { item ->
                Row(Modifier.fillMaxWidth().clickable { open = false; item.onClick() }.bottomRule().padding(horizontal = 14.dp, vertical = 13.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(item.label, color = if (item.danger) CrdcColors.Danger else CrdcColors.Blue, fontSize = 15.sp)
                    if (item.count > 0) {
                        Spacer(Modifier.width(8.dp))
                        Text(item.count.toString(), color = Color.White, fontSize = 11.sp, modifier = Modifier.clip(CircleShape)
                            .background(CrdcColors.Danger).padding(horizontal = 7.dp, vertical = 1.dp))
                    }
                }
            }
        }
    }
}

/** Change password (needs a connection: the server checks the council's password rules). */
@Composable
fun ChangePasswordScreen(sdk: CouncilSdk, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var old by remember { mutableStateOf("") }
    var new1 by remember { mutableStateOf("") }
    var new2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<Pair<String, MessageKind>?>(null) }
    AppScreen("Change password", onBack = onBack) {
        ScrollColumn {
            msg?.let { Message(it.first, it.second) }
            Field("Old password", old, { old = it }, password = true)
            Field("New password", new1, { new1 = it }, password = true)
            Field("New password confirmation", new2, { new2 = it }, password = true,
                error = if (new2.isNotEmpty() && new1 != new2) "The two passwords do not match." else null)
            Text("At least 8 characters; not too similar to your name; not a common password; not entirely numeric.", fontSize = 12.sp, color = CrdcColors.Muted)
            PrimaryButton("Change my password", busy = busy, enabled = old.isNotBlank() && new1.length >= 8 && new1 == new2, onClick = {
                busy = true
                scope.launch {
                    msg = runCatching { sdk.changePassword(old, new1) }.fold(
                        { old = ""; new1 = ""; new2 = ""; "Your password was changed." to MessageKind.SUCCESS },
                        { (it.message ?: "Could not reach the council server – you need a connection to change your password.") to MessageKind.ERROR })
                    busy = false
                }
            })
        }
    }
}
