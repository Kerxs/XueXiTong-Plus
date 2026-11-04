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
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BatteryChargingFull
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        UiPrefs.load(this)
        TaskService.createChannels(this)
        // The splash runs on a fresh start only, not when the activity is recreated (rotation, theme).
        val splash = savedInstanceState == null
        setContent { AppTheme { AppRoot(splash) } }
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

private const val ONBOARDING_VERSION = 1
private fun prefs(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)

fun hasNotificationPermission(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
    ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

@Composable
fun AppRoot(splash: Boolean) {
    val ctx = LocalContext.current
    val c = X.colors
    val m = X.motion
    var onboarded by remember { mutableStateOf(prefs(ctx).getInt("onboarding", 0) >= ONBOARDING_VERSION) }
    var loadError by remember { mutableStateOf("") }
    var phase by remember { mutableStateOf(if (splash && m.enabled) SplashPhase.Splash else SplashPhase.Done) }
    val bg by animateColorAsState(c.bg, m.slowSpec(), label = "bg")

    LaunchedEffect(Unit) {
        Brand.iconRect = null
        runCatching { SettingsModel.load(ctx) }.onFailure {
            loadError = "运行组件加载失败：${it.message}"
            phase = SplashPhase.Done
        }
    }

    Box(Modifier.fillMaxSize().background(bg)) {
        when {
            loadError.isNotEmpty() -> Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                Text(loadError, color = c.danger)
            }
            !SettingsModel.loaded || phase == SplashPhase.Splash -> if (phase == SplashPhase.Done) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = c.accent) }
            }
            else -> {
                val brandHidden = phase != SplashPhase.Done
                PageSwitch(target = onboarded, index = { if (it) 1 else 0 }) { done ->
                    if (!done) {
                        OnboardingScreen(brandHidden, onDone = {
                            prefs(ctx).edit().putInt("onboarding", ONBOARDING_VERSION).apply()
                            onboarded = true
                        })
                    } else {
                        MainShell(brandHidden, reopenGuide = {
                            prefs(ctx).edit().putInt("onboarding", 0).apply()
                            onboarded = false
                        })
                    }
                }
            }
        }
        SplashOverlay(
            loaded = SettingsModel.loaded,
            status = "正在加载运行组件",
            phase = phase,
            onPhase = { phase = it },
        )
    }
}

@Composable
private fun MainShell(brandHidden: Boolean, reopenGuide: () -> Unit) {
    val c = X.colors
    val m = X.motion
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val snackbar = remember { SnackbarHostState() }
    // Fade only (no lift), so the brand icon the splash logo flies to stays where it is.
    val shell = remember { Animatable(if (m.enabled) 0f else 1f) }
    LaunchedEffect(Unit) { shell.animateTo(1f, tween(m.slow, easing = OutCubic)) }
    val itemColors = NavigationBarItemDefaults.colors(
        selectedIconColor = c.accent, selectedTextColor = c.text, indicatorColor = c.accentSoft,
        unselectedIconColor = c.muted, unselectedTextColor = c.muted,
    )
    Scaffold(
        containerColor = c.bg,
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            BrandRow(brandHidden, Modifier.windowInsetsPadding(WindowInsets.statusBars)
                .padding(start = Dimens.pad, end = Dimens.pad, top = 10.dp, bottom = 2.dp))
        },
        bottomBar = {
            Column(Modifier.graphicsLayer { alpha = shell.value }) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(c.border))
                NavigationBar(containerColor = c.pane) {
                    NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, colors = itemColors,
                        icon = { Icon(Icons.Filled.PlayCircle, null) }, label = { Text("运行面板") })
                    NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, colors = itemColors,
                        icon = { Icon(Icons.Filled.Settings, null) }, label = { Text("设置") })
                    NavigationBarItem(selected = tab == 2, onClick = { tab = 2 }, colors = itemColors,
                        icon = { Icon(Icons.Filled.BatteryChargingFull, null) }, label = { Text("后台保活") })
                }
            }
        },
    ) { padding ->
        PageSwitch(target = tab, index = { it }, modifier = Modifier.padding(padding).graphicsLayer { alpha = shell.value }) { page ->
            when (page) {
                0 -> RunScreen(snackbar, openSettings = { tab = 1 }, openKeepAlive = { tab = 2 })
                1 -> SettingsScreen(snackbar, reopenGuide = reopenGuide)
                else -> KeepAliveScreen()
            }
        }
    }
    RunDialogs()
}
