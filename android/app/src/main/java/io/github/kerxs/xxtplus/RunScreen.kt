package io.github.kerxs.xxtplus

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.WebView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.toMutableStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Spacer(Modifier.size(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("学习通PLUS", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            StatusPill()
        }
        Spacer(Modifier.size(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { start() }, enabled = !RunState.running, modifier = Modifier.weight(1f)) { Text("开始运行") }
            val paused = RunState.paused
            Button(
                onClick = { TaskService.send(ctx, if (paused) TaskService.ACTION_RESUME else TaskService.ACTION_PAUSE) },
                enabled = RunState.running,
                colors = if (paused) ButtonDefaults.buttonColors() else ButtonDefaults.buttonColors(
                    containerColor = Colors.warningSoft, contentColor = Colors.warning),
                modifier = Modifier.weight(1f),
            ) { Text(if (paused) "继续" else "暂停") }
            Button(
                onClick = { TaskService.send(ctx, TaskService.ACTION_STOP) },
                enabled = RunState.running,
                colors = ButtonDefaults.buttonColors(containerColor = Colors.dangerSoft, contentColor = Colors.danger),
                modifier = Modifier.weight(1f),
            ) { Text("停止") }
        }
        if (!KeepAlive.isIgnoringBatteryOptimizations(ctx)) {
            Spacer(Modifier.size(8.dp))
            Card(Modifier.fillMaxWidth().clickable { openKeepAlive() }) {
                Text("还没有关闭电池优化，息屏后任务可能被系统停止。点这里设置后台保活。",
                    Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall, color = Colors.warning)
            }
        }
        Spacer(Modifier.size(8.dp))
        Stats()
        Spacer(Modifier.size(8.dp))
        var tab by rememberSaveable { mutableIntStateOf(0) }
        TabRow(selectedTabIndex = tab) {
            listOf("任务", "视频", "答题", "日志").forEachIndexed { i, t ->
                Tab(selected = tab == i, onClick = { tab = i }, text = { Text(t) })
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth().padding(top = 8.dp)) {
            when (tab) {
                0 -> ProgressPane()
                1 -> VideoPane()
                2 -> WorkPane()
                else -> LogPane()
            }
        }
    }
}

@Composable
private fun StatusPill() {
    val (text, fg, bg) = when {
        RunState.running && RunState.paused -> Triple("已暂停", MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.primaryContainer)
        RunState.running -> Triple("正在运行", Colors.success, Colors.successSoft)
        else -> Triple("未运行", MaterialTheme.colorScheme.onSurfaceVariant, MaterialTheme.colorScheme.surfaceVariant)
    }
    Row(Modifier.background(bg, RoundedCornerShape(50)).padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(fg, CircleShape))
        Spacer(Modifier.width(6.dp))
        Text(text, color = fg, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
    }
}

@Composable
private fun Stats() {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(RunState.running) {
        while (RunState.running) { now = System.currentTimeMillis(); delay(1000) }
    }
    val elapsed = if (RunState.running && RunState.startedAt > 0) (now - RunState.startedAt) / 1000 else 0
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            StatLine("当前课程", RunState.course.ifEmpty { "—" })
            StatLine("当前章节", RunState.chapter.ifEmpty { "—" })
            Row {
                Box(Modifier.weight(1f)) { StatLine("已完成任务", RunState.finishedTasks.toString()) }
                Box(Modifier.weight(1f)) {
                    StatLine("运行时长", "%02d:%02d:%02d".format(elapsed / 3600, elapsed % 3600 / 60, elapsed % 60))
                }
            }
        }
    }
}

@Composable
private fun StatLine(label: String, value: String) {
    Row {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.width(72.dp))
        Text(value, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun ProgressPane() {
    val items = RunState.progress.values.toList()
    if (items.isEmpty()) {
        Empty("还没有音视频任务")
        return
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items(items, key = { it.name }) { p ->
            Column {
                Row {
                    Text(p.name, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
                    Text("${p.done} / ${p.total}", style = MaterialTheme.typography.bodySmall)
                }
                LinearProgressIndicator(progress = { p.percent / 100f }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
            }
        }
    }
}

@Composable
private fun Empty(text: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
    val source = RunState.videoSource
    if (!RunState.running || !allowedVideo(source)) {
        Empty(if (RunState.running) "等待视频任务…" else "运行后在这里显示当前视频（静音）")
        return
    }
    Column {
        Text(RunState.videoTitle, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.size(6.dp))
        // The page's base URL makes WebView send a 学习通 Referer, which the video CDN requires.
        AndroidView(
            modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Color.Black),
            factory = { c ->
                WebView(c).apply {
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
        Spacer(Modifier.size(6.dp))
        Text("预览静音、不可操作，只用于查看当前任务。", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun WorkPane() {
    if (RunState.questions.isEmpty()) {
        Empty("章节检测出现时在这里显示题目和答案")
        return
    }
    val phase = when (RunState.workPhase) {
        "questions" -> "查找答案中"; "filled" -> "已填写，准备提交"; "submitted" -> "已提交"
        "saved" -> "已保存（未提交）"; "failed" -> "提交失败"; else -> RunState.workPhase
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Text("${RunState.workTitle} · $phase · 覆盖率 ${RunState.workCoverRate}%",
                style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        }
        items(RunState.questions, key = { it.index }) { q ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("${q.index}. ${q.title}", style = MaterialTheme.typography.bodyMedium)
                    if (q.options.isNotBlank()) Text(q.options, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("答案：" + q.answer.ifEmpty { if (RunState.workPhase == "questions") "查找中" else "—" },
                            Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
                        val (label, color) = when {
                            q.answer.isEmpty() -> "" to Color.Unspecified
                            q.source == "random" -> "随机作答" to Colors.warning
                            q.origin == "ai" -> "AI匹配" to MaterialTheme.colorScheme.primary
                            else -> "题库匹配" to Colors.success
                        }
                        if (label.isNotEmpty()) Text(label, color = color, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LogPane() {
    var filter by rememberSaveable { mutableStateOf("ALL") }
    val shown = RunState.logs.filter {
        when (filter) {
            "WARNING" -> it.level == "WARNING"
            "ERROR" -> it.level == "ERROR" || it.level == "CRITICAL"
            else -> true
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(shown.size) { if (shown.isNotEmpty()) list.scrollToItem(shown.size - 1) }
    Column {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("ALL" to "全部", "WARNING" to "警告", "ERROR" to "错误").forEach { (k, l) ->
                FilterChip(selected = filter == k, onClick = { filter = k }, label = { Text(l) })
            }
        }
        if (shown.isEmpty()) {
            Empty("暂无日志")
            return@Column
        }
        LazyColumn(state = list, modifier = Modifier.fillMaxSize()) {
            items(shown) { line ->
                val color = when (line.level) {
                    "ERROR", "CRITICAL" -> Colors.danger
                    "WARNING" -> Colors.warning
                    "SUCCESS" -> Colors.success
                    else -> MaterialTheme.colorScheme.onSurface
                }
                Text(
                    (if (line.time.isNotEmpty()) line.time.takeLast(12).take(8) + "  " else "") + line.message,
                    color = color, fontFamily = FontFamily.Monospace, fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 2.dp),
                )
            }
        }
    }
}

/** The worker waits on input(): course choice when no course ID is set, or a Y/n question. */
@Composable
fun RunDialogs() {
    val ctx = LocalContext.current
    RunState.prompt?.let { text ->
        AlertDialog(
            onDismissRequest = {},
            title = { Text("需要确认") },
            text = { Text(text) },
            confirmButton = { TextButton(onClick = { RunState.prompt = null; TaskService.send(ctx, TaskService.ACTION_ANSWER, "y") }) { Text("继续") } },
            dismissButton = { TextButton(onClick = { RunState.prompt = null; TaskService.send(ctx, TaskService.ACTION_ANSWER, "n") }) { Text("不继续") } },
        )
    }
    RunState.courses?.let { courses ->
        val checked = remember(courses) { courses.map { false }.toMutableStateList() }
        AlertDialog(
            onDismissRequest = {},
            title = { Text("选择要学习的课程") },
            text = {
                Column(Modifier.heightIn(max = 420.dp).verticalScroll(rememberScrollState())) {
                    Text("不勾选则学习全部课程。", style = MaterialTheme.typography.bodySmall)
                    courses.forEachIndexed { i, c ->
                        Row(Modifier.fillMaxWidth().clickable { checked[i] = !checked[i] }, verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = checked[i], onCheckedChange = null)
                            Spacer(Modifier.width(8.dp))
                            Text(c.title)
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val ids = courses.filterIndexed { i, _ -> checked[i] }.map { it.courseId }.distinct().joinToString(",")
                    RunState.courses = null
                    TaskService.send(ctx, TaskService.ACTION_ANSWER, ids)
                }) { Text("开始") }
            },
        )
    }
}
