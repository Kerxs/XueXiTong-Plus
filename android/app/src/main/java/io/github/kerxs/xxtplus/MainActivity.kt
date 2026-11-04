package io.github.kerxs.xxtplus

import android.Manifest
import android.content.Context
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BatteryChargingFull
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        TaskService.createChannels(this)
        setContent { AppTheme { AppRoot() } }
    }

    override fun onStart() {
        super.onStart()
        ContextCompat.registerReceiver(this, RunState.receiver, IntentFilter(TaskService.ACTION_EVENT),
            ContextCompat.RECEIVER_NOT_EXPORTED)
        RunState.sync(this)
    }

    override fun onStop() {
        unregisterReceiver(RunState.receiver)
        super.onStop()
    }
}

object Colors {
    val accent = Color(0xFF2563EB)
    val success = Color(0xFF15803D)
    val successSoft = Color(0xFFDCFCE7)
    val warning = Color(0xFFB45309)
    val warningSoft = Color(0xFFFEF3C7)
    val danger = Color(0xFFDC2626)
    val dangerSoft = Color(0xFFFEE2E2)
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val scheme = if (isSystemInDarkTheme()) {
        darkColorScheme(primary = Color(0xFF8AB4FF), secondary = Color(0xFF8AB4FF))
    } else {
        lightColorScheme(primary = Colors.accent, secondary = Colors.accent)
    }
    MaterialTheme(colorScheme = scheme, content = content)
}

private const val ONBOARDING_VERSION = 1
private fun prefs(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)

fun hasNotificationPermission(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
    ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

@Composable
fun AppRoot() {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var onboarded by remember { mutableStateOf(prefs(ctx).getInt("onboarding", 0) >= ONBOARDING_VERSION) }
    var loadError by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        runCatching { SettingsModel.load(ctx) }.onFailure { loadError = "运行组件加载失败：${it.message}" }
    }

    if (!SettingsModel.loaded) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            if (loadError.isEmpty()) CircularProgressIndicator() else Text(loadError, color = MaterialTheme.colorScheme.error)
        }
        return
    }
    if (!onboarded) {
        OnboardingScreen(onDone = {
            prefs(ctx).edit().putInt("onboarding", ONBOARDING_VERSION).apply()
            onboarded = true
        })
        return
    }

    var tab by rememberSaveable { mutableIntStateOf(0) }
    val snackbar = remember { SnackbarHostState() }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = tab == 0, onClick = { tab = 0 },
                    icon = { Icon(Icons.Filled.PlayCircle, null) }, label = { Text("运行") })
                NavigationBarItem(selected = tab == 1, onClick = { tab = 1 },
                    icon = { Icon(Icons.Filled.Settings, null) }, label = { Text("设置") })
                NavigationBarItem(selected = tab == 2, onClick = { tab = 2 },
                    icon = { Icon(Icons.Filled.BatteryChargingFull, null) }, label = { Text("后台保活") })
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            when (tab) {
                0 -> RunScreen(snackbar, openSettings = { tab = 1 }, openKeepAlive = { tab = 2 })
                1 -> SettingsScreen(snackbar, reopenGuide = {
                    prefs(ctx).edit().putInt("onboarding", 0).apply()
                    onboarded = false
                })
                else -> KeepAliveScreen()
            }
        }
    }
    RunDialogs()
}
