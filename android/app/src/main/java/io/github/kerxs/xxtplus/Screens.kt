package io.github.kerxs.xxtplus

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.launch

// ------------------------------------------------------------------ 设置

@Composable
fun SettingsScreen(snackbar: SnackbarHostState, reopenGuide: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("设置", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text("账号与运行", style = MaterialTheme.typography.titleMedium)
        BasicFieldsCard()
        SettingsModel.groups().forEach { SettingsGroupCard(it) }
        Button(onClick = {
            scope.launch {
                SettingsModel.save(ctx)
                val problem = SettingsModel.problem(ctx)
                snackbar.showSnackbar(if (problem.isEmpty()) "已保存" else "已保存。$problem")
            }
        }, modifier = Modifier.fillMaxWidth()) { Text("保存") }
        if (RunState.running) {
            Text("正在运行的任务使用开始时的设置，修改在下次开始时生效。", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        TextButton(onClick = reopenGuide) { Text("重新打开开始引导") }
        Text("账号、密码保存在本应用的私有目录，卸载应用会一并删除。", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    val tick = rememberResumeTick()
    val ignoring = remember(tick) { KeepAlive.isIgnoringBatteryOptimizations(ctx) }
    val notifications = remember(tick) { hasNotificationPermission(ctx) }
    val vendor = remember { KeepAlive.vendor() }
    val askNotify = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("视频要按真实时长上报进度，任务会运行很久。下面几项能让它在息屏和切到后台时继续运行；运行时建议连接充电器。",
            style = MaterialTheme.typography.bodyMedium)
        StepCard(
            title = "1. 允许通知",
            body = "运行时会显示常驻通知（可在通知里暂停 / 停止），这是系统允许后台长时间运行的前提。",
            done = notifications,
            action = "允许通知",
            onAction = {
                if (android.os.Build.VERSION.SDK_INT >= 33) askNotify.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                else KeepAlive.openNotificationSettings(ctx)
            },
        )
        StepCard(
            title = "2. 关闭电池优化",
            body = "让系统在息屏后不限制本应用的网络和计时。",
            done = ignoring,
            action = "关闭电池优化",
            onAction = { KeepAlive.requestIgnoreBatteryOptimizations(ctx) },
        )
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("3. 自启动与后台运行（${vendor.name}）", style = MaterialTheme.typography.titleSmall)
                Text("这些开关由手机厂商提供，应用无法替你打开，请按下面的步骤手动设置：",
                    style = MaterialTheme.typography.bodySmall)
                vendor.steps.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { KeepAlive.openAutostartSettings(ctx) }) { Text("打开自启动设置") }
                    OutlinedButton(onClick = { KeepAlive.openAppDetails(ctx) }) { Text("应用详情") }
                }
                Text("如果按钮打开的不是对应页面，请在系统设置里按上面的路径查找（不同系统版本位置略有不同）。",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Text("即使都设置好，也不能保证所有机型都不会被系统停止。被停止后重新点“开始运行”即可，学习通会保留已看的进度。",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun StepCard(title: String, body: String, done: Boolean, action: String, onAction: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row {
                Text(title, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                Text(if (done) "已完成" else "未设置", color = if (done) Colors.success else Colors.warning,
                    style = MaterialTheme.typography.labelMedium)
            }
            Text(body, style = MaterialTheme.typography.bodySmall)
            if (!done) Button(onClick = onAction) { Text(action) }
        }
    }
}

@Composable
fun KeepAliveScreen() {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("后台保活", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
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

/** 欢迎 > 免责声明 > 账号 > 答题来源 > 推送服务 > 后台保活 */
@Composable
fun OnboardingScreen(onDone: () -> Unit) {
    val ctx = LocalContext.current
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

    fun next() = scope.launch {
        SettingsModel.save(ctx)
        if (step < steps.size - 1) step++ else onDone()
    }

    Column(Modifier.fillMaxSize().systemBarsPadding().padding(16.dp)) {
        Text("开始引导 · ${steps[step]}", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Spacer(Modifier.size(8.dp))
        LinearProgressIndicator(progress = { (step + 1f) / steps.size }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.size(12.dp))
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            when (step) {
                0 -> {
                    Text("欢迎使用学习通PLUS 手机版", style = MaterialTheme.typography.titleMedium)
                    Text("接下来几步完成：阅读免责声明、填写学习通账号、选择章节检测的答题来源、配置推送服务，以及设置后台保活。之后都可以在“设置”里修改。")
                }
                1 -> {
                    Card(Modifier.fillMaxWidth()) {
                        SelectionContainer { Text(DISCLAIMER, Modifier.padding(16.dp), style = MaterialTheme.typography.bodySmall) }
                    }
                    Text("请在下面完整输入一遍上面的声明（空格和换行不计）：", style = MaterialTheme.typography.bodySmall)
                    OutlinedTextField(value = typed, onValueChange = { typed = it }, modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp),
                        placeholder = { Text("在这里输入免责声明全文") },
                        supportingText = { Text("${normalize(typed).length} / ${target.length}") })
                }
                2 -> {
                    Text("填写学习通手机号和密码。课程 ID 可以留空，开始运行时再选择。", style = MaterialTheme.typography.bodySmall)
                    BasicFieldsCard()
                }
                3 -> {
                    SettingsModel.group("tiku")?.let { SettingsGroupCard(it) }
                    SettingsModel.group("answer")?.let { SettingsGroupCard(it) }
                    if (problem.isNotEmpty()) Text(problem, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
                4 -> {
                    Text("任务结束或出错时推送到手机上的其他应用（例如微信里的 Server酱）。不需要可以选“不推送”。",
                        style = MaterialTheme.typography.bodySmall)
                    SettingsModel.group("notify")?.let { SettingsGroupCard(it, showTitle = false) }
                }
                else -> KeepAliveContent()
            }
        }
        Spacer(Modifier.size(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (step > 0) OutlinedButton(onClick = { step-- }) { Text("上一步") }
            Spacer(Modifier.weight(1f))
            if (step in 2..4) TextButton(onClick = { next() }) { Text("稍后配置") }
            Button(onClick = { next() }, enabled = canNext) { Text(if (step == steps.size - 1) "开始使用" else "下一步") }
        }
    }
}
