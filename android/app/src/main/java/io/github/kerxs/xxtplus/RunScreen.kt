package io.github.kerxs.xxtplus

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.WebView
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
import androidx.compose.material3.AlertDialog
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

    fun start() = scope.launch {
        val problem = SettingsModel.problem(ctx)
        if (problem.isNotEmpty()) {
            openSettings()
            snackbar.showSnackbar(problem)
            return@launch
        }
        SettingsModel.save(ctx)
        RunState.reset()
        if (hasNotificationPermission(ctx)) TaskService.send(ctx, TaskService.ACTION_START)
        else notifyPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
    }

    Column(Modifier.fillMaxSize().padding(horizontal = Dimens.pad), verticalArrangement = Arrangement.spacedBy(Dimens.gap)) {
        Spacer(Modifier.size(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("运行面板", color = c.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text("开始、暂停和查看任务进度", color = c.muted, fontSize = 12.sp)
            }
            StatusPill(
                kind = when { RunState.running && RunState.paused -> "paused"; RunState.running -> "running"; else -> "idle" },
                text = when { RunState.running && RunState.paused -> "已暂停"; RunState.running -> "正在运行"; else -> "未运行" },
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            XButton("开始运行", { start() }, Modifier.weight(1f), Kind.Primary, enabled = !RunState.running)
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
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(Dimens.radius)).background(c.warningSoft)
                .clickable { openKeepAlive() }.padding(horizontal = 12.dp, vertical = 10.dp)) {
                Text("后台保活未完成（${missing.joinToString("、") { it.first }}），息屏或切到后台后任务可能被系统停止。点这里设置。",
                    color = c.warning, fontSize = 12.sp)
            }
        }
        Stats()
        var tab by rememberSaveable { mutableStateOf("tasks") }
        val tabs = listOf("tasks" to "任务", "video" to "视频", "work" to "答题", "log" to "日志")
        Segmented(tabs, tab, { tab = it }, Modifier.fillMaxWidth())
        PageSwitch(tab, { t -> tabs.indexOfFirst { it.first == t } }, Modifier.weight(1f).fillMaxWidth()) { t ->
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

@Composable
private fun Stats() {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(RunState.running) {
        while (RunState.running) { now = System.currentTimeMillis(); delay(1000) }
    }
    val elapsed = if (RunState.running && RunState.startedAt > 0) (now - RunState.startedAt) / 1000 else 0
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("当前课程", RunState.course, Modifier.weight(1f), appearDelay = 0)
            StatTile("当前章节", RunState.chapter, Modifier.weight(1f), appearDelay = 60)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("已完成任务", "", Modifier.weight(1f), count = RunState.finishedTasks, appearDelay = 120)
            StatTile("运行时长", if (RunState.running) "%02d:%02d:%02d".format(elapsed / 3600, elapsed % 3600 / 60, elapsed % 60) else "",
                Modifier.weight(1f), appearDelay = 180)
        }
    }
}

@Composable
private fun Empty(text: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text, color = X.colors.faint, fontSize = 13.sp)
    }
}

@Composable
private fun ProgressPane() {
    val c = X.colors
    val items = RunState.progress.values.toList()
    if (items.isEmpty()) { Empty("还没有音视频任务"); return }
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

private fun attr(s: String) = s.replace("&", "&amp;").replace("\"", "&quot;").replace("<", "&lt;").replace(">", "&gt;")

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun VideoPane() {
    val c = X.colors
    val source = RunState.videoSource
    if (!RunState.running || !allowedVideo(source)) {
        Empty(if (RunState.running) "等待视频任务…" else "运行后在这里显示当前视频（静音）")
        return
    }
    XCard(Modifier.fillMaxWidth(), title = RunState.videoTitle.ifEmpty { "学习通视频" }, subtitle = "静音预览，不可操作") {
        // The page's base URL makes WebView send a 学习通 Referer, which the video CDN requires.
        AndroidView(
            modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(Dimens.radius)).background(Color.Black),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.mediaPlaybackRequiresUserGesture = false
                    setBackgroundColor(android.graphics.Color.BLACK)
                }
            },
            update = { view ->
                if (view.tag != source) {
                    view.tag = source
                    val html = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
                        <style>html,body{margin:0;height:100%;background:#000}video{width:100%;height:100%;object-fit:contain;pointer-events:none}</style>
                        </head><body><video src="${attr(source)}" autoplay muted playsinline loop></video></body></html>"""
                    view.loadDataWithBaseURL("https://mooc1.chaoxing.com/", html, "text/html", "utf-8", null)
                }
            },
            onRelease = { it.destroy() },
        )
        Text("显示当前视频任务的画面，切换任务时自动更新。", color = c.faint, fontSize = 12.sp)
    }
}

@Composable
private fun WorkPane() {
    val c = X.colors
    if (RunState.questions.isEmpty()) { Empty("章节检测出现时在这里显示题目和答案"); return }
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
    var filter by rememberSaveable { mutableStateOf("ALL") }
    val shown = RunState.logs.filter {
        when (filter) {
            "WARNING" -> it.level == "WARNING"
            "ERROR" -> it.level == "ERROR" || it.level == "CRITICAL"
            else -> true
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(shown.size) { if (shown.isNotEmpty()) list.animateScrollToItem(shown.size - 1) }
    XCard(Modifier.fillMaxSize(), padding = 12.dp) {
        Segmented(listOf("ALL" to "全部", "WARNING" to "警告", "ERROR" to "错误"), filter, { filter = it }, Modifier.fillMaxWidth())
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
fun RunDialogs() {
    val ctx = LocalContext.current
    val c = X.colors
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
