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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import kotlinx.coroutines.launch
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
        RunState.loadPreviewMode(this)
        RunState.sync(this)
        RunState.notificationsAllowed = hasNotificationPermission(this)
    }

    override fun onResume() {
        super.onResume()
        RunState.notificationsAllowed = hasNotificationPermission(this)
    }

    override fun onStop() {
        unregisterReceiver(RunState.receiver)
        super.onStop()
    }
}

private fun prefs(ctx: Context) = ctx.getSharedPreferences("app", Context.MODE_PRIVATE)

/**
 * Which pages of the guide to show (like ui/controller.onboarding_plan on the desktop). Someone who
 * finished an older guide only gets the pages that are new since then, and can skip them; the
 * disclaimer is asked again only when its text changes.
 */
object Guide {
    // 2: + 自动完成 step (1.2.8) · 3: + 匿名统计 (1.3.0)
    const val VERSION = 3
    const val TELEMETRY_PAGE = 5
    const val AUTO_PAGE = 3
    /** Bump when the DISCLAIMER text changes: everyone has to accept it once more. */
    const val DISCLAIMER_VERSION = 1
    const val DISCLAIMER_PAGE = 1
    /** Page index (as in OnboardingScreen) to the guide version that added or last changed it. */
    private val since = listOf(1, 1, 1, 2, 1, 3, 1)   // 欢迎, 免责声明, 账号, 自动完成, 答题来源, 匿名统计, 权限设置

    fun plan(seen: Int, disclaimer: Int): Pair<List<Int>, Boolean> {
        val needDisclaimer = disclaimer < DISCLAIMER_VERSION
        // The complete guide is four pages: 欢迎与声明 → 账号 → 答题来源 → 权限设置. The welcome text is
        // on the disclaimer page, and the 自动完成 / 匿名统计 switches (which have defaults) are at
        // the end of the 答题来源 page instead of a page each.
        if (seen <= 0) return since.indices.filter {
            it != 0 && it != AUTO_PAGE && it != TELEMETRY_PAGE && (it != DISCLAIMER_PAGE || needDisclaimer)
        } to false
        return since.indices.filter { i ->
            if (i == DISCLAIMER_PAGE) needDisclaimer else i != 0 && i != since.lastIndex && since[i] > seen
        } to true
    }

    fun plan(ctx: Context): Pair<List<Int>, Boolean> {
        val p = prefs(ctx)
        // Guides finished before the disclaimer had its own version: that was this text.
        if (!p.contains("disclaimer") && p.getInt("onboarding", 0) >= 1) p.edit().putInt("disclaimer", 1).apply()
        return plan(p.getInt("onboarding", 0), p.getInt("disclaimer", 0))
    }

    fun finish(ctx: Context) =
        prefs(ctx).edit().putInt("onboarding", VERSION).putInt("disclaimer", DISCLAIMER_VERSION).apply()

    fun reopen(ctx: Context) = prefs(ctx).edit().putInt("onboarding", 0).apply()
}

fun hasNotificationPermission(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
    ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

@Composable
fun AppRoot(splash: Boolean) {
    val ctx = LocalContext.current
    val c = X.colors
    val m = X.motion
    var guide by remember { mutableStateOf(Guide.plan(ctx)) }
    val onboarded = guide.first.isEmpty()
    var loadError by remember { mutableStateOf("") }
    var attempt by remember { mutableIntStateOf(0) }
    var phase by remember {
        mutableStateOf(if (splash && m.enabled && UiPrefs.splash) SplashPhase.Splash else SplashPhase.Done)
    }
    val bg by animateColorAsState(c.bg, m.slowSpec(), label = "bg")

    LaunchedEffect(attempt) {
        Brand.iconRect = null
        Brand.titleRect = null
        Courses.load(ctx)
        loadError = ""
        runCatching { SettingsModel.load(ctx) }.onFailure {
            // Fallback screen instead of a spinner forever: the reason, 重试, 复制错误信息.
            loadError = "运行组件加载失败：${it.javaClass.simpleName}: ${it.message}"
            phase = SplashPhase.Done
        }
    }
    // 自动检查更新 once the app is on screen (desktop: checkOnStartup).
    LaunchedEffect(phase, SettingsModel.loaded) {
        if (phase == SplashPhase.Done && SettingsModel.loaded && UiPrefs.autoUpdate && Updater.state == "idle") {
            Updater.check(ctx, quiet = true)
        }
    }
    // A task process the system killed must not stay "正在运行" (P1 / P3).
    LaunchedEffect(RunState.running) {
        while (RunState.running) {
            kotlinx.coroutines.delay(5000)
            if (RunState.running && !RunState.workerAlive(ctx)) RunState.workerLost(ctx)
        }
    }

    Box(Modifier.fillMaxSize().background(bg)) {
        when {
            loadError.isNotEmpty() -> LoadErrorScreen(loadError) { attempt++ }
            !SettingsModel.loaded || phase == SplashPhase.Splash -> if (phase == SplashPhase.Done) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = c.accent) }
            }
            else -> {
                val brandHidden = phase != SplashPhase.Done
                PageSwitch(target = onboarded, index = { if (it) 1 else 0 }) { done ->
                    if (!done) {
                        OnboardingScreen(brandHidden, order = guide.first, newOnly = guide.second, onDone = {
                            Guide.finish(ctx)
                            guide = Guide.plan(ctx)
                        })
                    } else {
                        MainShell(brandHidden, reopenGuide = {
                            Guide.reopen(ctx)
                            guide = Guide.plan(ctx)
                        })
                    }
                }
            }
        }
        SplashOverlay(
            loaded = SettingsModel.loaded || loadError.isNotEmpty(),
            status = "正在加载运行组件",
            phase = phase,
            onPhase = { phase = it },
        )
        if (Updater.showDialog) UpdateDialog()
        if (Courses.showPicker) CoursePickerDialog { ids ->
            Courses.showPicker = false
            if (ids != null) Courses.choose(ctx, ids)
        }
    }
}

@Composable
private fun LoadErrorScreen(message: String, retry: () -> Unit) {
    val c = X.colors
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(12.dp,
        Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("运行组件没有加载成功", color = c.text, fontSize = androidx.compose.ui.unit.TextUnit(18f, androidx.compose.ui.unit.TextUnitType.Sp))
        Text(message, color = c.danger)
        Text("可以重试；仍然失败请复制错误信息反馈。", color = c.muted)
        XButton("重试", retry, Modifier.fillMaxWidth(), Kind.Primary)
        XButton("复制错误信息", { clipboard.setText(androidx.compose.ui.text.AnnotatedString(message)) }, Modifier.fillMaxWidth())
    }
}

/** Desktop UpdateDialog.qml: version, notes, download progress, 下载并安装 / 稍后. */
@Composable
private fun UpdateDialog() {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val rel = Updater.release
    androidx.compose.material3.AlertDialog(
        onDismissRequest = { if (Updater.state != "downloading") Updater.showDialog = false },
        containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
        shape = androidx.compose.foundation.shape.RoundedCornerShape(Dimens.radiusLarge),
        title = {
            Text(when (Updater.state) {
                "available", "downloading", "ready" -> "发现新版本 ${rel?.version}"
                "latest" -> "已是最新版本"
                else -> "检查更新"
            })
        },
        text = {
            Column(Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp)) {
                when (Updater.state) {
                    "latest" -> Text("当前版本 ${Updater.currentVersion(ctx)} 已是最新。" + Updater.error)
                    "error" -> Text(Updater.error, color = c.danger)
                    else -> {
                        Text("当前版本 ${Updater.currentVersion(ctx)}", color = c.muted)
                        if (!rel?.notes.isNullOrBlank()) Text(rel!!.notes.take(1200))
                        if (Updater.state == "downloading") XProgress(Updater.progress)
                        if (Updater.error.isNotEmpty()) Text(Updater.error, color = c.warning)
                    }
                }
            }
        },
        confirmButton = {
            // A newer release is known: download (or retry after a failed download).
            val canDownload = rel != null && Updater.newer(rel.version, Updater.currentVersion(ctx))
            when {
                Updater.state == "downloading" ->
                    XButton("正在下载 ${(Updater.progress * 100).toInt()}%", {}, kind = Kind.Primary, enabled = false)
                Updater.state == "ready" ->
                    XButton("安装", { Updater.downloadedFile(ctx)?.let { Updater.install(ctx, it) } }, kind = Kind.Primary)
                canDownload && (Updater.state == "available" || Updater.state == "error") ->
                    XButton(if (Updater.state == "error") "重新下载" else "下载并安装",
                        { scope.launch { Updater.downloadAndInstall(ctx) } }, kind = Kind.Primary)
                else -> XButton("关闭", { Updater.showDialog = false })
            }
        },
        dismissButton = {
            if (Updater.state in setOf("available", "ready", "error") && rel != null) {
                XButton("稍后", { Updater.showDialog = false }, kind = Kind.Ghost)
            }
        },
    )
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
                        icon = { Icon(Icons.Filled.BatteryChargingFull, null) }, label = { Text("权限") })
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
    RunDialogs(openSettings = { tab = 1 })
}
