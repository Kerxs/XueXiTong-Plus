package io.github.kerxs.xxtplus

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.launch

@Composable
fun PageHeader(title: String, subtitle: String = "") {
    val c = X.colors
    Column {
        Text(title, color = c.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        if (subtitle.isNotEmpty()) Text(subtitle, color = c.muted, fontSize = 12.sp)
    }
}

// ------------------------------------------------------------------ 设置

@Composable
fun SettingsScreen(snackbar: SnackbarHostState, reopenGuide: () -> Unit) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Dimens.pad),
        verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        PageHeader("设置", "账号、答题来源、推送和界面")
        XCard(Modifier.fillMaxWidth(), title = "账号与运行", subtitle = "学习通账号和基本参数", appearDelay = 0) {
            BasicFields()
        }
        SettingsModel.groups().forEachIndexed { i, g -> SettingsGroupCard(g, appearDelay = 60 * (i + 1)) }
        XCard(Modifier.fillMaxWidth(), title = "界面", subtitle = "与电脑版相同的外观选项", appearDelay = 240) {
            Text("主题", color = c.text, fontSize = 14.sp)
            Segmented(listOf("system" to "跟随系统", "light" to "浅色", "dark" to "深色"), UiPrefs.theme,
                { UiPrefs.theme = it; UiPrefs.save(ctx) }, Modifier.fillMaxWidth())
            SwitchRow("界面动画", "关闭后所有过渡立即完成", UiPrefs.motion) { UiPrefs.motion = it; UiPrefs.save(ctx) }
        }
        XButton("保存", {
            scope.launch {
                SettingsModel.save(ctx)
                val problem = SettingsModel.problem(ctx)
                snackbar.showSnackbar(if (problem.isEmpty()) "已保存" else "已保存。$problem")
            }
        }, Modifier.fillMaxWidth(), Kind.Primary)
        if (RunState.running) {
            Text("正在运行的任务使用开始时的设置，修改在下次开始时生效。", color = c.muted, fontSize = 12.sp)
        }
        XButton("重新打开开始引导", reopenGuide, Modifier.fillMaxWidth(), Kind.Secondary)
        Text("账号、密码保存在本应用的私有目录，卸载应用会一并删除。", color = c.faint, fontSize = 12.sp)
    }
}

@Composable
fun SwitchRow(label: String, hint: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    val c = X.colors
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label, color = c.text, fontSize = 14.sp)
            if (hint.isNotEmpty()) Text(hint, color = c.muted, fontSize = 12.sp)
        }
        Switch(checked = checked, onCheckedChange = onChange, colors = switchColors())
    }
}

// ------------------------------------------------------------------ 后台保活

/** Re-reads system state whenever the user comes back from a settings page. */
@Composable
private fun rememberResumeTick(): Int {
    var tick by remember { mutableIntStateOf(0) }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) tick++ }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    return tick
}

@Composable
fun KeepAliveContent() {
    val ctx = LocalContext.current
    val c = X.colors
    val tick = rememberResumeTick()
    val ignoring = remember(tick) { KeepAlive.isIgnoringBatteryOptimizations(ctx) }
    val notifications = remember(tick) { hasNotificationPermission(ctx) }
    val vendor = remember { KeepAlive.vendor() }
    var autostart by remember { mutableStateOf(KeepAlive.autostartConfirmed(ctx)) }
    val askNotify = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }  // re-read on resume

    Column(verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        Text("视频要按真实时长上报进度，任务会运行很久。请完成下面三项，任务才能在息屏和切到后台时继续运行；运行时建议连接充电器。",
            color = c.text, fontSize = 14.sp)
        StepCard(
            title = "1. 允许通知",
            body = "运行时显示常驻通知（可在通知里暂停 / 停止），需要选择课程或确认时提醒你。",
            consequence = KeepAlive.CONSEQUENCE_NOTIFY, done = notifications, action = "允许通知", appearDelay = 0,
            onAction = {
                if (android.os.Build.VERSION.SDK_INT >= 33) askNotify.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                else KeepAlive.openNotificationSettings(ctx)
            },
        )
        StepCard(
            title = "2. 关闭电池优化",
            body = "让系统在息屏后不限制本应用的网络和计时。点按钮后在系统弹窗里选“允许”。",
            consequence = KeepAlive.CONSEQUENCE_BATTERY, done = ignoring, action = "关闭电池优化", appearDelay = 60,
            onAction = { KeepAlive.requestIgnoreBatteryOptimizations(ctx) },
        )
        XCard(Modifier.fillMaxWidth(), appearDelay = 120) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("3. 自启动与后台运行", color = c.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                StatusPill(if (autostart) "running" else "idle", if (autostart) "已确认" else "未设置")
            }
            Text("${vendor.name}：这些开关由手机厂商提供，应用无法替你打开，也无法检测是否已打开。请按下面的步骤手动设置：",
                color = c.text, fontSize = 13.sp)
            vendor.steps.forEach { Text("• $it", color = c.text, fontSize = 13.sp) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                XButton("打开自启动设置", { KeepAlive.openAutostartSettings(ctx) }, Modifier.weight(1f))
                XButton("应用详情", { KeepAlive.openAppDetails(ctx) }, Modifier.weight(1f))
            }
            Text("如果按钮打开的不是对应页面，请在系统设置里按上面的路径查找（不同系统版本位置略有不同）。",
                color = c.muted, fontSize = 12.sp)
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).clickable {
                autostart = !autostart; KeepAlive.setAutostartConfirmed(ctx, autostart)
            }, verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = autostart, onCheckedChange = null, colors = checkboxColors())
                Text("我已按上面的步骤设置好", color = c.text, fontSize = 14.sp)
            }
            Consequence(KeepAlive.CONSEQUENCE_AUTOSTART, visible = !autostart)
        }
        Text("即使都设置好，也不能保证所有机型都不会被系统停止。被停止后重新点“开始运行”即可，学习通会保留已看的进度。",
            color = c.muted, fontSize = 12.sp)
    }
}

@Composable
private fun Consequence(text: String, visible: Boolean = true) {
    val c = X.colors
    val m = X.motion
    AnimatedVisibility(visible, enter = fadeIn(tween(m.normal)) + expandVertically(tween(m.normal)),
        exit = fadeOut(tween(m.fast)) + shrinkVertically(tween(m.normal))) {
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).background(c.dangerSoft)
            .padding(horizontal = 10.dp, vertical = 8.dp)) {
            Text(text, color = c.danger, fontSize = 12.sp)
        }
    }
}

@Composable
private fun StepCard(title: String, body: String, consequence: String, done: Boolean, action: String,
                     appearDelay: Int, onAction: () -> Unit) {
    val c = X.colors
    XCard(Modifier.fillMaxWidth(), appearDelay = appearDelay) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = c.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            StatusPill(if (done) "running" else "idle", if (done) "已完成" else "未设置")
        }
        Text(body, color = c.text, fontSize = 13.sp)
        Consequence(consequence, visible = !done)
        AnimatedVisibility(!done) { XButton(action, onAction, Modifier.fillMaxWidth(), Kind.Primary) }
    }
}

@Composable
fun KeepAliveScreen() {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Dimens.pad),
        verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        PageHeader("后台保活", "让任务在息屏和后台时继续运行")
        KeepAliveContent()
    }
}

// ------------------------------------------------------------------ 开始引导

const val DISCLAIMER = "1. 本软件基于开源项目 Samueli924/chaoxing，遵循 GPL-3.0 协议，仅供学习交流使用，禁止用于任何盈利用途，修改或衍生版本必须同样开源。\n" +
    "2. 本软件与超星、学习通官方无任何关联，不代表其立场。\n" +
    "3. 使用自动化工具可能违反学习通的用户协议及所在学校的课程或学术诚信规定，可能导致账号受限、封禁或成绩作废。是否使用、如何使用由你自行判断，相关后果由你自行承担。\n" +
    "4. 账号、密码和 cookies 以明文保存在本应用的私有目录，请自行保管手机，不要在他人的设备上使用。\n" +
    "5. 本软件按“现状”提供，不对运行结果、答题正确率或任何直接、间接损失作任何保证或承担责任。\n" +
    "6. 他人或组织使用本软件进行的任何违法违规行为，与作者无关。"

private fun normalize(s: String) = s.replace(Regex("\\s+"), "")

/** Desktop Onboarding.qml step indicator: dots fill and turn into checks, connectors fill as you advance. */
@Composable
private fun StepIndicator(count: Int, step: Int) {
    val c = X.colors
    val m = X.motion
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        for (i in 0 until count) {
            val reached = i <= step
            val bg by animateColorAsState(if (reached) c.accent else c.surfaceAlt, m.normalSpec(), label = "dot")
            val sc by animateFloatAsState(if (i == step) 1.08f else 1f, tween(m.normal, easing = OutBack), label = "dotS")
            Box(Modifier.size(26.dp).scale(sc).clip(CircleShape).background(bg)
                .border(1.dp, if (reached) c.accent else c.border, CircleShape), contentAlignment = Alignment.Center) {
                if (i < step) Icon(Icons.Filled.Check, null, tint = c.accentText, modifier = Modifier.size(14.dp))
                else Text("${i + 1}", color = if (reached) c.accentText else c.muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            }
            if (i < count - 1) {
                val fill by animateFloatAsState(if (i < step) 1f else 0f, m.slowSpec(), label = "line")
                Box(Modifier.weight(1f).padding(horizontal = 4.dp).height(2.dp).clip(RoundedCornerShape(1.dp)).background(c.border)) {
                    Box(Modifier.fillMaxHeight().fillMaxWidth(fill).background(c.accent))
                }
            }
        }
    }
}

/** 欢迎 > 免责声明 > 账号 > 答题来源 > 推送服务 > 后台保活 */
@Composable
fun OnboardingScreen(brandHidden: Boolean, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val steps = listOf("欢迎", "免责声明", "账号", "答题来源", "推送服务", "后台保活")
    var step by rememberSaveable { mutableIntStateOf(0) }
    var typed by rememberSaveable { mutableStateOf("") }
    var problem by remember { mutableStateOf("") }

    // Only the answer-source step blocks 下一步 (like the desktop guide); it can be skipped with 稍后配置.
    LaunchedEffect(step, SettingsModel.values.toMap()) {
        problem = if (step == 3) {
            val p = SettingsModel.problem(ctx)
            if (p.startsWith("还没有填写手机号")) "" else p
        } else ""
    }

    val target = remember { normalize(DISCLAIMER) }
    val canNext = when (step) {
        1 -> normalize(typed) == target
        3 -> problem.isEmpty()
        else -> true
    }

    var unfinished by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }

    fun next() = scope.launch {
        SettingsModel.save(ctx)
        when {
            step < steps.size - 1 -> step++
            KeepAlive.missing(ctx).isNotEmpty() -> unfinished = KeepAlive.missing(ctx)
            else -> onDone()
        }
    }

    if (unfinished.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { unfinished = emptyList() },
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("后台保活还没有完成") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("以下设置还没有完成，可能导致：", fontSize = 14.sp)
                    unfinished.forEach { (_, consequence) -> Consequence(consequence) }
                    Text("之后可以在“后台保活”页面继续设置。", color = c.muted, fontSize = 12.sp)
                }
            },
            confirmButton = { XButton("去完成设置", { unfinished = emptyList() }, kind = Kind.Primary) },
            dismissButton = { XButton("仍然开始", { unfinished = emptyList(); onDone() }, kind = Kind.Ghost) },
        )
    }

    Column(Modifier.fillMaxSize().systemBarsPadding().padding(Dimens.pad), verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        BrandRow(brandHidden)
        StepIndicator(steps.size, step)
        PageSwitch(step, { it }) { s -> PageHeader(steps[s], "开始引导 · 第 ${s + 1} / ${steps.size} 步") }
        PageSwitch(step, { it }, Modifier.weight(1f).fillMaxWidth()) { s ->
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
                when (s) {
                    0 -> XCard(Modifier.fillMaxWidth(), title = "欢迎使用学习通PLUS 手机版") {
                        Text("与电脑版使用同一套任务逻辑。接下来几步完成：", color = c.text, fontSize = 14.sp)
                        listOf("阅读免责声明", "填写学习通账号", "选择章节检测的答题来源", "配置推送服务",
                            "设置后台保活（允许通知、关闭电池优化、自启动与后台运行）").forEach {
                            Text("• $it", color = c.text, fontSize = 14.sp)
                        }
                        Text("之后都可以在“设置”和“后台保活”里修改。", color = c.muted, fontSize = 12.sp)
                    }
                    1 -> {
                        XCard(Modifier.fillMaxWidth(), padding = 14.dp) {
                            SelectionContainer { Text(DISCLAIMER, color = c.text, fontSize = 13.sp) }
                        }
                        Text("请在下面完整输入一遍上面的声明（空格和换行不计）：", color = c.muted, fontSize = 12.sp)
                        val done = normalize(typed).length
                        OutlinedTextField(value = typed, onValueChange = { typed = it },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp), shape = RoundedCornerShape(Dimens.radius),
                            placeholder = { Text("在这里输入免责声明全文") }, colors = fieldColors())
                        XProgress(done.toFloat() / target.length, color = if (canNext) c.success else c.accent)
                        Text("$done / ${target.length}", color = c.muted, fontSize = 12.sp)
                    }
                    2 -> XCard(Modifier.fillMaxWidth(), title = "学习通账号", subtitle = "课程 ID 可以留空，开始运行时再选择") { BasicFields() }
                    3 -> {
                        SettingsModel.group("tiku")?.let { SettingsGroupCard(it) }
                        SettingsModel.group("answer")?.let { SettingsGroupCard(it, appearDelay = 60) }
                        if (problem.isNotEmpty()) Consequence(problem)
                    }
                    4 -> {
                        Text("任务结束或出错时推送到手机上的其他应用（例如微信里的 Server酱）。不需要可以选“不推送”。",
                            color = c.muted, fontSize = 12.sp)
                        SettingsModel.group("notify")?.let { SettingsGroupCard(it) }
                    }
                    else -> KeepAliveContent()
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (step > 0) XButton("上一步", { step-- })
            Spacer(Modifier.weight(1f))
            if (step in 2..4) XButton("稍后配置", { next() }, kind = Kind.Ghost)
            XButton(if (step == steps.size - 1) "开始使用" else "下一步", { next() }, kind = Kind.Primary, enabled = canNext)
        }
    }
}
