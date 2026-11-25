package zw.gov.chipingerdc.shared.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import zw.gov.chipingerdc.shared.CouncilSdk

@Composable
fun LoginScreen(sdk: CouncilSdk, subtitle: String, footer: String, onRegister: (() -> Unit)? = null) {
    val scope = rememberCoroutineScope()
    var server by remember { mutableStateOf(sdk.session.baseUrl) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var showServer by remember { mutableStateOf(false) }

    Box(
        Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(CrdcColors.Green, CrdcColors.Blue))),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.widthIn(max = 460.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Chipinge Rural District Council", color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            Text(subtitle, color = Color.White.copy(alpha = 0.9f), textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            SectionCard {
                Field("Username", username, { username = it })
                Field("Password", password, { password = it }, password = true)
                if (showServer) Field("Server address", server, { server = it })
                if (error != null) InfoBox(error!!, CrdcColors.Danger)
                PrimaryButton("Log in", busy = busy, enabled = username.isNotBlank() && password.isNotBlank(), onClick = {
                    busy = true
                    error = null
                    scope.launch {
                        runCatching { sdk.login(server, username, password) }
                            .onFailure { error = it.message ?: "Could not reach the council server. Check your connection." }
                        busy = false
                    }
                })
                TextButton(onClick = { showServer = !showServer }) { Text(if (showServer) "Hide server settings" else "Server settings") }
                if (onRegister != null) TextButton(onClick = onRegister) { Text("New here? Create an account") }
            }
            Text(footer, color = Color.White.copy(alpha = 0.85f), fontSize = 12.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
    }
}
