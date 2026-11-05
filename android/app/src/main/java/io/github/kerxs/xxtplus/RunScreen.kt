package io.github.kerxs.xxtplus

import android.annotation.SuppressLint
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.Assignment
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ListAlt
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.OndemandVideo
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.toMutableStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun RunScreen(snackbar: SnackbarHostState, openSettings: () -> Unit, openKeepAlive: () -> Unit) {
    val ctx = LocalContext.current
    val c = X.colors
    val m = X.motion
    val scope = rememberCoroutineScope()
    val notifyPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        TaskService.send(ctx, TaskService.ACTION_START)  // runs either way; without it the notification is hidden
    }

    // Guards against double taps while the checks run and the service starts (P1: no duplicate starts).
    var starting by remember { mutableStateOf(false) }
    LaunchedEffect(RunState.running) { if (RunState.running) starting = false }

    fun start() {
        if (starting || RunState.running) return
        starting = true
        scope.launch {
            val problem = SettingsModel.problem(ctx)
            if (problem.isNotEmpty()) {
                starting = false
                openSettings()
                snackbar.showSnackbar(problem)
                return@launch
            }
            SettingsModel.save(ctx)
            RunState.reset()
            if (hasNotificationPermission(ctx)) TaskService.send(ctx, TaskService.ACTION_START)
            else notifyPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
            delay(8000)
            starting = false  // the service never answered: allow another try
        }
    }

    val accountMissing = SettingsModel.values["common.use_cookies"] != "true" &&
        (SettingsModel.values["common.username"].isNullOrBlank() || SettingsModel.values["common.password"].isNullOrBlank())

    // Short screens: the header, reminders and tiles leave no room for the panes, so the whole
    // panel scrolls and the panes get a fixed height instead of the remaining space.
    androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxSize()) {
    val compact = maxHeight < 640.dp
    val outer = if (compact) Modifier.fillMaxSize().verticalScroll(rememberScrollState()) else Modifier.fillMaxSize()
    Column(outer.padding(horizontal = Dimens.pad), verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        Spacer(Modifier.size(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("运行面板", color = c.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text("开始、暂停和查看任务进度", color = c.muted, fontSize = 12.sp)
            }
            // Same states as the desktop status: 正在运行 / 已暂停 / 已完成 / 已停止 / 已退出 / 未运行.
            val (kind, label) = when {
                RunState.running && RunState.paused -> "paused" to "已暂停"
                RunState.running -> "running" to "正在运行"
                starting -> "paused" to "正在启动"
                RunState.lastResult == "done" -> "done" to "已完成"
                RunState.lastResult == "stopped" -> "idle" to "已停止"
                RunState.lastResult == "error" -> "error" to "已退出"
                else -> "idle" to "未运行"
            }
            StatusPill(kind, label)
        }
        AnimatedVisibility(accountMissing, enter = fadeIn(tween(m.normal)) + expandVertically(tween(m.normal)),
            exit = fadeOut(tween(m.fast)) + shrinkVertically(tween(m.normal))) {
            Banner("还没有配置账号。请到“设置 → 账号”填写账号密码，或开启 cookies 登录。", c.warningSoft, c.warning) { openSettings() }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            XButton(if (starting) "正在启动…" else "开始运行", { start() }, Modifier.weight(1f), Kind.Primary,
                enabled = !RunState.running && !starting)
            val paused = RunState.paused
            XButton(if (paused) "继续" else "暂停",
                { TaskService.send(ctx, if (paused) TaskService.ACTION_RESUME else TaskService.ACTION_PAUSE) },
                Modifier.weight(1f), if (paused) Kind.Primary else Kind.Warning, enabled = RunState.running)
            XButton("停止", { TaskService.send(ctx, TaskService.ACTION_STOP) }, Modifier.weight(1f), Kind.Danger,
                enabled = RunState.running)
        }
        val missing = KeepAlive.missing(ctx)
        AnimatedVisibility(missing.isNotEmpty(), enter = fadeIn(tween(m.normal)) + expandVertically(tween(m.normal)),
            exit = fadeOut(tween(m.fast)) + shrinkVertically(tween(m.normal))) {
            Banner("权限设置未完成（${missing.joinToString("、") { it.first }}），息屏或切到后台后任务可能被系统停止。点这里设置。",
                c.warningSoft, c.warning) { openKeepAlive() }
        }
        CourseRow(snackbar)
        AnimatedVisibility(RunState.manualTasks.isNotEmpty(), enter = fadeIn(tween(m.normal)) + expandVertically(tween(m.normal)),
            exit = fadeOut(tween(m.fast)) + shrinkVertically(tween(m.normal))) {
            Banner("有 ${RunState.manualTasks.size} 项内容需要手动完成（文档、阅读、问卷等），点这里查看",
                c.accentSoft, c.accent) { RunState.showManualDialog = true }
        }
        Stats()
        var tab by rememberSaveable { mutableStateOf("tasks") }
        val tabs = listOf("tasks" to "任务", "video" to "视频", "work" to "答题", "log" to "日志")
        Segmented(tabs, tab, { tab = it }, Modifier.fillMaxWidth())
        val paneModifier = if (compact) Modifier.height(420.dp).fillMaxWidth() else Modifier.weight(1f).fillMaxWidth()
        PageSwitch(tab, { t -> tabs.indexOfFirst { it.first == t } }, paneModifier) { t ->
            Box(Modifier.fillMaxSize().padding(bottom = 8.dp)) {
                when (t) {
                    "tasks" -> ProgressPane()
                    "video" -> VideoPane()
                    "work" -> WorkPane()
                    else -> LogPane()
                }
            }
        }
    }
    }
}

/** Desktop BasicParams: which courses will run, and 识别课程. */
@Composable
private fun CourseRow(snackbar: SnackbarHostState) {
    val ctx = LocalContext.current
    val c = X.colors
    val scope = rememberCoroutineScope()
    val names = Courses.selectedNames()
    val ids = SettingsModel.values["common.course_list"].orEmpty()
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radiusLarge)).background(c.surface)
        .border(1.dp, c.border, RoundedCornerShape(Dimens.radiusLarge)).padding(start = 12.dp, end = 10.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("课程", color = c.muted, fontSize = 12.sp)
            Text(when {
                names.isNotEmpty() -> names.joinToString("、")
                ids.isNotBlank() -> "课程 ID $ids"
                else -> "开始运行时选择"
            }, color = c.text, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        XButton(if (Courses.state == "running") "识别中…" else "识别课程", {
            scope.launch { Courses.detect(ctx)?.let { if (Courses.state == "error") snackbar.showSnackbar(it) } }
        }, kind = Kind.Secondary, enabled = Courses.state != "running" && !RunState.running)
    }
}

@Composable
private fun Stats() {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(RunState.running, RunState.paused) {
        while (RunState.running) { now = System.currentTimeMillis(); delay(1000) }
    }
    val elapsed = RunState.elapsedSeconds(now)  // paused time not counted, as on the desktop
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("当前课程", RunState.course, Modifier.weight(1f), appearDelay = 0, icon = Icons.Outlined.MenuBook)
            StatTile("当前章节", RunState.chapter, Modifier.weight(1f), appearDelay = 60, icon = Icons.Outlined.ListAlt)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("已完成任务", "", Modifier.weight(1f), count = RunState.finishedTasks, appearDelay = 120, icon = Icons.Outlined.CheckCircle)
            StatTile("运行时长", if (RunState.running) "%02d:%02d:%02d".format(elapsed / 3600, elapsed % 3600 / 60, elapsed % 60) else "",
                Modifier.weight(1f), appearDelay = 180, icon = Icons.Outlined.AccessTime)
        }
    }
}

@Composable
private fun Empty(text: String, icon: ImageVector? = null) {
    val c = X.colors
    Box(Modifier.fillMaxSize().clip(RoundedCornerShape(Dimens.radiusLarge)).background(c.surface)
        .border(1.dp, c.border, RoundedCornerShape(Dimens.radiusLarge)).padding(Dimens.pad), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (icon != null) Icon(icon, null, Modifier.size(28.dp), tint = c.faint)
            Text(text, color = c.faint, fontSize = 13.sp)
        }
    }
}

/** Desktop accountBanner: soft fill, coloured border, large radius; tap to act. */
@Composable
private fun Banner(text: String, bg: Color, fg: Color, onClick: () -> Unit) {
    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radiusLarge)).background(bg)
        .border(1.dp, fg.copy(alpha = 0.45f), RoundedCornerShape(Dimens.radiusLarge))
        .clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 10.dp)) {
        Text(text, color = fg, fontSize = 12.sp, lineHeight = 18.sp)
    }
}

@Composable
private fun ProgressPane() {
    val c = X.colors
    val items = RunState.progress.values.toList()
    if (items.isEmpty()) { Empty("还没有音视频任务", Icons.Outlined.OndemandVideo); return }
    XCard(Modifier.fillMaxSize(), title = "音视频任务", subtitle = "${items.count { it.percent >= 100 }} / ${items.size} 已完成") {
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(items, key = { it.name }) { p ->
                Column(Modifier.animateItem(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row {
                        Text(p.name, Modifier.weight(1f), color = c.text, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("${p.done} / ${p.total}", color = c.muted, fontSize = 12.sp)
                    }
                    XProgress(p.percent / 100f, color = if (p.percent >= 100) c.success else c.accent)
                }
            }
        }
    }
}

/** Only addresses from the 学习通 video status response, like the desktop preview (ui/videoproxy.py). */
private fun allowedVideo(source: String): Boolean {
    val uri = runCatching { Uri.parse(source) }.getOrNull() ?: return false
    val host = uri.host?.lowercase() ?: return false
    return uri.scheme in listOf("http", "https") &&
        listOf("chaoxing.com", "cldisk.com").any { host == it || host.endsWith(".$it") }
}

private var lastPreviewRefresh = 0L

/** The preview failed 3 times: ask the task to read the video status again (fresh address). */
private fun requestFreshPreview(ctx: android.content.Context) {
    val now = System.currentTimeMillis()
    if (now - lastPreviewRefresh < 90_000) return
    lastPreviewRefresh = now
    runCatching { java.io.File(PythonBridge.dataDir(ctx), "preview_refresh.flag").writeText("refresh") }
}

@Composable
private fun VideoPane() {
    val c = X.colors
    val source = RunState.videoSource
    if (!RunState.running || !allowedVideo(source)) {
        Empty(if (RunState.running) "等待视频任务…" else "运行后在这里显示当前视频（静音）", Icons.Outlined.Videocam)
        return
    }
    var player by remember { mutableStateOf<PreviewPlayer?>(null) }
    var state by remember { mutableStateOf("loading") }
    // Desktop VideoView: start where the task is, re-sync when it drifts, pause with the task.
    LaunchedEffect(source, player) {
        val view = player ?: return@LaunchedEffect
        while (true) {
            delay(3000)
            view.sync(RunState.videoPosition(), RunState.paused)
        }
    }
    XCard(Modifier.fillMaxWidth(), title = RunState.videoTitle.ifEmpty { "学习通视频" }, subtitle = "静音预览，不可操作") {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(Dimens.radius)).background(Color.Black),
            contentAlignment = Alignment.Center) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    PreviewPlayer(ctx).also { p ->
                        p.onState = { state = it }
                        p.onGiveUp = { requestFreshPreview(ctx) }
                        player = p
                    }
                },
                update = { view -> view.show(source, RunState.videoPosition()) },
                onRelease = { view -> if (player === view) player = null; view.release() },
            )
            when (state) {
                "loading" -> Text("正在加载视频…", color = Color.White.copy(alpha = 0.7f), fontSize = 13.sp)
                "retrying" -> Text("视频加载失败，正在重试…", color = Color.White.copy(alpha = 0.8f), fontSize = 13.sp)
                "error" -> Text("视频暂时无法加载，正在重试（不影响任务运行）", color = Color.White.copy(alpha = 0.8f), fontSize = 13.sp)
            }
        }
        Text("与任务进度同步，1 倍速播放。", color = c.faint, fontSize = 12.sp)
    }
}
@Composable
private fun WorkPane() {
    val c = X.colors
    if (RunState.questions.isEmpty()) { Empty("章节检测出现时在这里显示题目和答案", Icons.Outlined.Assignment); return }
    val phase = when (RunState.workPhase) {
        "questions" -> "查找答案中"; "filled" -> "已填写，准备提交"; "submitted" -> "已提交"
        "saved" -> "已保存（未提交）"; "failed" -> "提交失败"; else -> RunState.workPhase
    }
    val (pillKind, _) = when (RunState.workPhase) {
        "submitted" -> "running" to 0; "failed" -> "error" to 0; "questions" -> "paused" to 0; else -> "idle" to 0
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(RunState.workTitle.ifEmpty { "章节检测" }, color = c.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("覆盖率 ${RunState.workCoverRate}%", color = c.muted, fontSize = 12.sp)
                }
                StatusPill(pillKind, phase)
            }
        }
        itemsIndexed(RunState.questions, key = { _, q -> q.index }) { i, q ->
            Box(Modifier.animateItem()) {
                QuestionCard(q, pending = RunState.workPhase == "questions" && q.answer.isEmpty(), revealDelay = i * 120)
            }
        }
    }
}

@Composable
private fun LogPane() {
    val c = X.colors
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    var filter by rememberSaveable { mutableStateOf("ALL") }
    var copied by remember { mutableStateOf(false) }
    val shown = RunState.logs.filter {
        when (filter) {
            "INFO" -> it.level in setOf("INFO", "SUCCESS", "DEBUG")
            "WARNING" -> it.level == "WARNING"
            "ERROR" -> it.level == "ERROR" || it.level == "CRITICAL"
            else -> true
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(shown.size) { if (shown.isNotEmpty()) list.animateScrollToItem(shown.size - 1) }
    LaunchedEffect(copied) { if (copied) { delay(1500); copied = false } }
    XCard(Modifier.fillMaxSize(), padding = 12.dp) {
        Segmented(listOf("ALL" to "全部", "INFO" to "信息", "WARNING" to "警告", "ERROR" to "错误"), filter, { filter = it },
            Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            XButton(if (copied) "已复制" else "复制", {
                clipboard.setText(androidx.compose.ui.text.AnnotatedString(
                    shown.joinToString("\n") { (if (it.time.isNotEmpty()) it.time + " " else "") + "[${it.level}] " + it.message }))
                copied = true
            }, Modifier.weight(1f), enabled = shown.isNotEmpty())
            XButton("清空", { RunState.logs.clear() }, Modifier.weight(1f), enabled = RunState.logs.isNotEmpty())
        }
        if (shown.isEmpty()) { Empty("暂无日志"); return@XCard }
        LazyColumn(state = list, modifier = Modifier.fillMaxSize()) {
            items(shown) { line ->
                Row(Modifier.padding(vertical = 3.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (line.time.isNotEmpty()) Text(line.time.takeLast(12).take(8), color = c.faint,
                        fontFamily = FontFamily.Monospace, fontSize = 11.sp)
                    Text(line.message, color = if (line.level == "INFO" || line.level == "DEBUG") c.text else c.levelColor(line.level),
                        fontFamily = FontFamily.Monospace, fontSize = 12.sp)
                }
            }
        }
    }
}

/** The worker waits on input(): course choice when no course ID is set, or a Y/n question. */
@Composable
fun RunDialogs(openSettings: () -> Unit = {}) {
    val ctx = LocalContext.current
    val c = X.colors
    if (RunState.showManualDialog && RunState.manualTasks.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { RunState.showManualDialog = false },
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("有内容需要手动完成") },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("下面的内容程序无法自动完成，需要你到学习通手动完成：", color = c.muted, fontSize = 13.sp)
                    RunState.manualTasks.forEach { t ->
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).background(c.surfaceAlt)
                            .padding(horizontal = 10.dp, vertical = 8.dp)) {
                            Text(t.kind + if (t.name.isNotEmpty()) "「${t.name}」" else "", color = c.text, fontSize = 14.sp)
                            Text("${t.course} / ${t.chapter}", color = c.faint, fontSize = 12.sp)
                        }
                    }
                    if (!RunState.pushConfigured()) {
                        Text("在“设置 → 通知推送”选择本机通知后，会改为通知提醒。", color = c.muted, fontSize = 12.sp)
                    }
                }
            },
            confirmButton = { XButton("知道了", { RunState.showManualDialog = false }, kind = Kind.Primary) },
            dismissButton = {
                if (!RunState.pushConfigured()) XButton("设置通知", { RunState.showManualDialog = false; openSettings() }, kind = Kind.Ghost)
            },
        )
    }
    RunState.prompt?.let { text ->
        AlertDialog(
            onDismissRequest = {},
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("需要确认") },
            text = { Text(text) },
            confirmButton = { XButton("继续", { RunState.prompt = null; TaskService.send(ctx, TaskService.ACTION_ANSWER, "y") }, kind = Kind.Primary) },
            dismissButton = { XButton("不继续", { RunState.prompt = null; TaskService.send(ctx, TaskService.ACTION_ANSWER, "n") }) },
        )
    }
    RunState.courses?.let { courses ->
        val checked = remember(courses) { courses.map { false }.toMutableStateList() }
        AlertDialog(
            onDismissRequest = {},
            containerColor = c.surface, titleContentColor = c.text, textContentColor = c.text,
            shape = RoundedCornerShape(Dimens.radiusLarge),
            title = { Text("选择要学习的课程") },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("不勾选则学习全部课程。", color = c.muted, fontSize = 12.sp)
                    courses.forEachIndexed { i, course ->
                        Row(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius))
                                .background(if (checked[i]) c.accentSoft else c.surfaceAlt)
                                .border(1.dp, if (checked[i]) c.accent else c.border, RoundedCornerShape(Dimens.radius))
                                .clickable { checked[i] = !checked[i] }.padding(horizontal = 8.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(checked = checked[i], onCheckedChange = null,
                                colors = CheckboxDefaults.colors(checkedColor = c.accent, uncheckedColor = c.borderStrong))
                            Spacer(Modifier.width(8.dp))
                            Text(course.title, color = c.text, fontSize = 14.sp)
                        }
                    }
                }
            },
            confirmButton = {
                XButton("开始", {
                    val ids = courses.filterIndexed { i, _ -> checked[i] }.map { it.courseId }.distinct().joinToString(",")
                    RunState.courses = null
                    TaskService.send(ctx, TaskService.ACTION_ANSWER, ids)
                }, kind = Kind.Primary)
            },
        )
    }
}
