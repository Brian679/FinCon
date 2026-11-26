package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import zw.gov.chipingerdc.shared.CouncilSdk

/** Django admin login page: grey page, white box with the green/gold header. */
@Composable
fun LoginScreen(sdk: CouncilSdk, subtitle: String, footer: String, onRegister: (() -> Unit)? = null) {
    val scope = rememberCoroutineScope()
    var server by remember { mutableStateOf(sdk.session.baseUrl) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showServer by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().background(CrdcColors.Darkened), contentAlignment = Alignment.Center) {
        Column(
            Modifier.widthIn(max = 420.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp)
                .border(1.dp, CrdcColors.Hairline).background(androidx.compose.ui.graphics.Color.White),
        ) {
            Text(LocalSiteName.current, color = CrdcColors.Gold, fontSize = 22.sp, fontWeight = FontWeight.Light,
                modifier = Modifier.fillMaxWidth().background(CrdcColors.Green).padding(horizontal = 18.dp, vertical = 16.dp))
            Box(Modifier.fillMaxWidth().height(3.dp).background(CrdcColors.Gold))
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(subtitle, color = CrdcColors.Muted, fontSize = 13.sp)
                if (error != null) Message(error!!, MessageKind.ERROR)
                Field("Username", username, { username = it })
                Field("Password", password, { password = it }, password = true)
                if (showServer) Field("Server address", server, { server = it })
                PrimaryButton("Log in", busy = busy, enabled = username.isNotBlank() && password.isNotBlank(), onClick = {
                    busy = true
                    error = null
                    scope.launch {
                        runCatching { sdk.login(server, username, password) }
                            .onFailure { error = it.message ?: "Could not reach the council server. Check your connection." }
                        busy = false
                    }
                })
                Text(if (showServer) "Hide server settings" else "Server settings", color = CrdcColors.Blue, fontSize = 13.sp,
                    modifier = Modifier.clickable { showServer = !showServer })
                if (onRegister != null) Text("No account yet? Create one – it is free", color = CrdcColors.Blue, fontSize = 13.sp,
                    modifier = Modifier.clickable { onRegister() })
                Text(footer, color = CrdcColors.Muted, fontSize = 12.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}
